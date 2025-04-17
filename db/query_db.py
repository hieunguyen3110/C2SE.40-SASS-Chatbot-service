import pymongo
from bson.json_util import dumps

class QueryDB:
    def __init__(self,
                 mongodbUri: str,
                 dbName: str,
                 dbCollection: str
                 ):
        self.client = pymongo.MongoClient(mongodbUri)
        self.db = self.client[dbName]
        self.collection = self.db[dbCollection]

    def insert_data(self,contents):
        self.collection.insert_many([{"title": doc["title"],"content": doc["content"],"file_name": doc["file_name"],"doc_id": doc["doc_id"], "embeddings": doc["embeddings"]} for doc in contents])

    def get_document_by_id(self,docIds):
        query = {"doc_id": {"$in": docIds}}
        projection = {"file_name": 0, "embeddings": 0, "title": 0, "_id": 0}
        documents = list(self.collection.find(query,projection))
        return documents

    def clear_data(self):
        self.collection.delete_many({})