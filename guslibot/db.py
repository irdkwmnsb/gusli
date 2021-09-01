import motor.motor_asyncio
import pymongo
from motor.core import AgnosticClient
from pymongo.collection import Collection
from pymongo.database import Database

from guslibot.config import MONGO_URL, DBNAME

index_coros = []

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)  # type: AgnosticClient
db = client[DBNAME]  # type: Database
users = db["users"]  # type: Collection
# shape:
# _id
# user_id
# display_name
# tag
# perm_list

chats = db["chats"]  # type: Collection
# shape:
# _id
# perm_list
