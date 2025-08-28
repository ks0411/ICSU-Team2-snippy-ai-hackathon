# Module for Azure Cosmos DB operations:
# - Manage singleton client, database, and container
# - Configure container with vector index for embeddings
# - Upsert and retrieve code snippet documents with embeddings
# - Perform vector similarity search using DiskANN index

import os
import logging
from typing import Any
from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.core.credentials import AzureKeyCredential
from azure.identity.aio import DefaultAzureCredential

# Configure logging for this module
logger = logging.getLogger(__name__)

# Constants for Cosmos DB configuration
COSMOS_DATABASE_NAME = os.environ.get("COSMOS_DATABASE_NAME", "dev-snippet-db")
COSMOS_CONTAINER_NAME = os.environ.get("COSMOS_CONTAINER_NAME", "code-snippets")
COSMOS_VECTOR_TOP_K = int(os.environ.get("COSMOS_VECTOR_TOP_K", "30"))

# Singleton references for client, database, and container caching
# This ensures we reuse connections across calls
_cosmos_client = None
_database = None
_container = None

# Gets or creates the singleton Cosmos client, caching it for reuse
async def get_cosmos_client():
    """
    Gets or creates the singleton Cosmos client.
    """
    global _cosmos_client
    if _cosmos_client is None:
        logger.debug("Creating Cosmos client")
        _cosmos_client = CosmosClient(
            url=os.environ["COSMOS_ENDPOINT"],
            credential=os.environ["COSMOS_KEY"]
        )
    return _cosmos_client

# Gets or creates the singleton Cosmos database reference
async def get_database():
    """
    Gets or creates the singleton database.
    """
    global _database
    if _database is None:
        client = await get_cosmos_client()
        _database = await client.create_database_if_not_exists(COSMOS_DATABASE_NAME)
    return _database

# Gets or creates the Cosmos DB container with proper partition key and vector index configuration
# The container is set up with a partition on /name and a vectorEmbeddingPolicy on /embedding
async def get_container():
    """
    Gets or creates the Cosmos DB container with proper partition key and vector index configuration.
    
    The container is configured with:
    - Partition key: /name (for now, will be migrated to /projectId later)
    - Vector embedding policy: int8, 1536 dimensions, cosine distance
    - Excluded path: /embedding/* (to avoid regular indexing of vector data)
    
    Returns:
        The container client
        
    Raises:
        Exception: If container creation or configuration fails
    """
    global _container
    if _container is None:
        try:
            logger.info(f"Getting container '{COSMOS_CONTAINER_NAME}' from database '{COSMOS_DATABASE_NAME}'")
            
            database = await get_database()
            # Create container with vector index configuration
            logger.debug("Creating container with vector index configuration")
            indexing_policy: Any = {
                "indexingMode": "consistent",
                "automatic": True,
                "includedPaths": [
                    {
                        "path": "/*"
                    }
                ],
                "excludedPaths": [
                    {
                        "path": "/embedding/*"
                    }
                ],
                "vectorEmbeddingPolicy": {
                    "vectorEmbeddings": [
                        {
                            "path": "/embedding",
                            "dataType": "int8",
                            "dimensions": 1536,
                            "distanceFunction": "cosine"
                        }
                    ]
                }
            }
            _container = await database.create_container_if_not_exists(
                id=COSMOS_CONTAINER_NAME,
                partition_key=PartitionKey(path="/name"),
                indexing_policy=indexing_policy
            )
            
            logger.info("Successfully configured container with vector index")
        except Exception as e:
            logger.error(f"Error configuring Cosmos container: {str(e)}", exc_info=True)
            raise
    return _container


# Closes all Cosmos DB connections and resets cached client, database, and container
async def close_connections():
    """
    Closes all Cosmos DB connections.
    """
    global _cosmos_client, _database, _container
    if _cosmos_client is not None:
        await _cosmos_client.close()
        _cosmos_client = None
        _database = None
        _container = None
        logger.info("Closed Cosmos DB connections")


# Upserts a document into Cosmos DB with vector embeddings
# The document includes id, name, projectId, code, type, and embedding fields
async def upsert_document(name: str, project_id: str, code: str, embedding: list, language: str = None, description: str = None) -> dict:
    """Upserts a code snippet document with (optionally) quantized embedding."""
    try:
        logger.info(f"Upserting snippet '{name}' (project={project_id})")

        if not isinstance(embedding, list):
            raise ValueError("Embedding must be a list of floats")

        # Simple int8 quantization (scale -1..1 -> -127..127) if floats provided
        quantized_embedding = []
        for v in embedding:
            try:
                # Clamp then scale
                fv = float(v)
                if fv > 1:
                    fv = 1.0
                if fv < -1:
                    fv = -1.0
                q = int(fv * 127)
                quantized_embedding.append(q)
            except Exception:  # pragma: no cover - defensive
                quantized_embedding.append(0)

        doc = {
            "id": name,
            "name": name,
            "projectId": project_id,
            "code": code,
            "language": language,
            "description": description,
            "type": "code-snippet",
            "embedding": quantized_embedding,
        }

        container = await get_container()
        stored = await container.upsert_item(doc)
        logger.info(f"Upserted snippet '{name}' successfully")
        # Return a trimmed response (exclude full embedding for payload size)
        stored_copy = dict(stored)
        if "embedding" in stored_copy:
            stored_copy["embedding_length"] = len(stored_copy.pop("embedding"))
        return stored_copy
    except Exception as e:
        logger.error(f"Error upserting document: {e}", exc_info=True)
        raise

# Retrieves all snippets from Cosmos DB
# Returns a list of all snippet documents
async def list_all_snippets() -> list[dict]:
    """
    Gets all snippets from Cosmos DB.
    
    Returns:
        List of all snippet documents
        
    Raises:
        Exception: If query execution fails
    """
    try:
        logger.info("Retrieving all snippets")
        
        container = await get_container()
        
        # Query all snippet documents
        sql = "SELECT c.id, c.name, c.projectId, c.code FROM c WHERE c.type = 'code-snippet'"
        
        logger.debug(f"Executing SQL query: {sql}")
        items_iterable = container.query_items(query=sql)
        
        results = [item async for item in items_iterable]
        logger.info(f"Found {len(results)} snippets")
        
        return results
    except Exception as e:
        logger.error(f"Error listing snippets: {str(e)}", exc_info=True)
        raise

async def list_snippets_by_project(project_id: str) -> list[dict]:
    """Gets all snippets for a given project from Cosmos DB."""
    try:
        logger.info(f"Retrieving snippets for project '{project_id}'")
        container = await get_container()
        sql = (
            "SELECT c.id, c.name, c.projectId, c.code "
            "FROM c WHERE c.type = 'code-snippet' AND c.projectId = @pid"
        )
        params = [{"name": "@pid", "value": project_id}]
        logger.debug(f"Executing SQL query: {sql} with project_id={project_id}")
        items_iterable = container.query_items(query=sql, parameters=params)
        results = [item async for item in items_iterable]
        logger.info(f"Found {len(results)} snippets for project '{project_id}'")
        return results
    except Exception as e:
        logger.error(f"Error listing snippets by project: {str(e)}", exc_info=True)
        raise

# Retrieves a snippet by its id (partition key) from Cosmos DB
# Returns the document or None if not found
async def get_snippet_by_id(name: str) -> dict | None:
    """
    Gets a snippet from Cosmos DB by id.
    
    Args:
        name: The name (id) of the snippet to retrieve
        
    Returns:
        The retrieved document or None if not found
        
    Raises:
        Exception: If document retrieval fails
    """
    try:
        logger.info(f"Retrieving snippet with id '{name}'")
        
        container = await get_container()
        
        try:
            result = await container.read_item(
                item=name,
                partition_key=name
            )
            logger.info(f"Successfully retrieved snippet with id '{name}'")
            return result
        except CosmosResourceNotFoundError:
            logger.info(f"No snippet found with id '{name}'")
            return None
                
    except Exception as e:
        logger.error(f"Error retrieving snippet: {str(e)}", exc_info=True)
        raise

# Performs vector similarity search using Cosmos DB's DiskANN index
# Returns the top-k similar snippet documents with their distance scores
async def query_similar_snippets(
    query_vector: list[float], *, project_id: str, k: int = COSMOS_VECTOR_TOP_K
) -> list[dict]:
    """
    Performs vector similarity search using Cosmos DB's DiskANN index.
    
    The query:
    ```sql
    SELECT TOP @k c.id, c.code, 
    VectorDistance(c.embedding, @vec) AS score 
    FROM c WHERE c.projectId = @pid 
    ORDER BY VectorDistance(c.embedding, @vec)
    ```
    
    Args:
        query_vector: The query embedding vector
        project_id: The project ID to search within
        k: Number of results to return
        
    Returns:
        List of matching documents with their scores:
        [
            {"id": "snippet-1", "code": "...", "score": 0.95},
            {"id": "snippet-2", "code": "...", "score": 0.92},
            ...
        ]
        
    Raises:
        Exception: If query execution fails
    """
    try:
        logger.info(f"Executing vector similarity search (k={k}, project_id={project_id})")
        logger.debug(f"Query vector length: {len(query_vector)}")
        
        container = await get_container()

        params = [
            {"name": "@vec", "value": query_vector},
            {"name": "@k", "value": k},
            {"name": "@pid", "value": project_id},
        ]

        sql = (
            "SELECT TOP @k c.id, c.code, "
            "VectorDistance(c.embedding, @vec) AS score "
            "FROM c WHERE c.projectId = @pid "
            "ORDER BY VectorDistance(c.embedding, @vec)"
        )

        logger.debug(f"Executing SQL query: {sql}")
        items_iterable = container.query_items(
            query=sql,
            parameters=params
        )
        
        results = [item async for item in items_iterable]
        logger.info(f"Found {len(results)} similar snippets")
        
        return results
    except Exception as e:
        logger.error(f"Error in vector similarity search: {str(e)}", exc_info=True)
        raise 