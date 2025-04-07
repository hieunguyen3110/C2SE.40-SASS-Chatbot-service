import pymongo

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
        self.collection.insert_many([{"title": doc["title"],"content": doc["content"],"file_name": doc["file_name"], "embeddings": doc["embeddings"]} for doc in contents])

    def clear_data(self):
        self.collection.delete_many({})