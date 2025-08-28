# =============================================================================
#
# This application demonstrates a modern AI-powered code snippet manager built with:
#
# 1. Azure Functions - Serverless compute that runs your code in the cloud
#    - HTTP triggers - Standard RESTful API endpoints accessible over HTTP
#    - MCP triggers - Model Context Protocol for AI agent integration (e.g., GitHub Copilot)
#
# 2. Azure Cosmos DB - NoSQL database with vector search capability
#    - Stores code snippets and their vector embeddings
#    - Enables semantic search through vector similarity
#
# 3. Azure OpenAI - Provides AI models and embeddings
#    - Generates vector embeddings from code snippets
#    - These embeddings capture the semantic meaning of the code
#
# 4. Azure AI Agents - Specialized AI agents for code analysis
#    - For generating documentation and style guides from snippets
#
# The application provides two parallel interfaces for the same functionality:
# - HTTP endpoints for traditional API access
# - MCP tools for AI assistant integration

import json
import logging
import os
import azure.functions as func
from typing import Any, Dict

from azure.storage.blob.aio import BlobServiceClient  # type: ignore

try:
    # Lazy import inside health check will also work, but importing here to surface import errors early
    from data import cosmos_ops  # type: ignore
except Exception as import_err:  # pragma: no cover - defensive
    logging.error(f"Failed to import cosmos_ops during startup: {import_err}")

app = func.FunctionApp()

# Register blueprints with enhanced error handling to prevent startup issues

# Core snippy functionality
try:
    from functions import bp_snippy
    app.register_blueprint(bp_snippy.bp)
    logging.info("✅ Snippy blueprint registered successfully")
except ImportError as e:
    logging.error(f"❌ Import error for Snippy blueprint: {e}")
except Exception as e:
    logging.error(f"❌ Snippy blueprint registration failed: {e}")

# Query functionality  
try:
    from routes import query
    app.register_blueprint(query.bp)
    logging.info("✅ Query blueprint registered successfully")
except ImportError as e:
    logging.error(f"❌ Import error for Query blueprint: {e}")
except Exception as e:
    logging.error(f"❌ Query blueprint registration failed: {e}")

# Embeddings functionality - now enabled for Level 2
try:
    from functions import bp_embeddings
    app.register_blueprint(bp_embeddings.bp)
    logging.info("✅ Embeddings blueprint registered successfully")
except ImportError as e:
    logging.error(f"❌ Import error for Embeddings blueprint: {e}")
except Exception as e:
    logging.error(f"❌ Embeddings blueprint registration failed: {e}")

# Ingestion functionality - blob trigger for Level 4
try:
    from functions import bp_ingestion
    app.register_blueprint(bp_ingestion.bp)
    logging.info("✅ Ingestion blueprint registered successfully")
except ImportError as e:
    logging.error(f"❌ Import error for Ingestion blueprint: {e}")
except Exception as e:
    logging.error(f"❌ Ingestion blueprint registration failed: {e}")

# Multi-agent functionality
try:
    from functions import bp_multi_agent
    app.register_blueprint(bp_multi_agent.bp)
    logging.info("✅ Multi-agent blueprint registered successfully")
except ImportError as e:
    logging.error(f"❌ Import error for Multi-agent blueprint: {e}")
except Exception as e:
    logging.error(f"❌ Multi-agent blueprint registration failed: {e}")


# =============================================================================
# HEALTH CHECK FUNCTIONALITY
# =============================================================================

# HTTP endpoint for health check
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
async def http_health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Health check endpoint to verify the service is running.
    
    Returns:
        JSON response with status "ok" and 200 status code
    """
    try:
        logging.info("Health check endpoint called")
        return func.HttpResponse(
            body=json.dumps({"status": "ok"}),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.error(f"Error in health check: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)}),
            mimetype="application/json",
            status_code=500
        )


# HTTP endpoint for health check
@app.route(route="health_extended", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
async def http_health_check_extended(req: func.HttpRequest) -> func.HttpResponse:
    """Extended health check including Storage & Cosmos connectivity."""
    logging.info("Extended health check endpoint called")

    storage_result: Dict[str, Any] = {"ok": False}
    cosmos_result: Dict[str, Any] = {"ok": False}

    # --- Storage account validation ---
    try:
        conn_str = os.environ.get("AzureWebJobsStorage") or os.environ.get("STORAGE_CONNECTION_STRING")
        ingestion_container = (
            os.environ.get("INGESTION_CONTAINER")
            or os.environ.get("STORAGE_CONTAINER_SNIPPETINPUT")
            or "snippet-input"
        )
        if not conn_str:
            raise ValueError("Missing AzureWebJobsStorage/ STORAGE_CONNECTION_STRING env var")

        blob_client = BlobServiceClient.from_connection_string(conn_str)
        container_client = blob_client.get_container_client(ingestion_container)
        await container_client.get_container_properties()
        storage_result.update(
            {
                "ok": True,
                "container": ingestion_container,
                "account_url": blob_client.url,
            }
        )
    except Exception as e:  # pragma: no cover - best effort diagnostics
        logging.error(f"Storage health check failed: {e}")
        storage_result.update({"error": str(e)})

    # --- Cosmos DB validation ---
    try:
        # Attempt to get (and if needed create) the container
        container = await cosmos_ops.get_container()  # type: ignore
        # Light-weight query: attempt a single iterator to ensure RU path works
        query_iter = container.query_items(query="SELECT TOP 1 c.id FROM c")
        _ = [item async for item in query_iter][:1]
        cosmos_result.update(
            {
                "ok": True,
                "database": os.environ.get("COSMOS_DATABASE_NAME"),
                "container": os.environ.get("COSMOS_CONTAINER_NAME"),
            }
        )
    except Exception as e:  # pragma: no cover
        logging.error(f"Cosmos health check failed: {e}")
        cosmos_result.update({"error": str(e)})

    overall_ok = storage_result.get("ok") and cosmos_result.get("ok")
    status = "ok" if overall_ok else "error"
    http_status = 200 if overall_ok else 500

    body = {
        "status": status,
        "storage": storage_result,
        "cosmos": cosmos_result,
    }

    return func.HttpResponse(
        body=json.dumps(body),
        mimetype="application/json",
        status_code=http_status,
    )