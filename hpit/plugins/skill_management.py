from hpitclient import Plugin

from pymongo import MongoClient
from bson.objectid import ObjectId
import bson

from couchbase import Couchbase
import couchbase

import requests

from hpit.management.settings_manager import SettingsManager
settings = SettingsManager.get_plugin_settings()

class SkillManagementPlugin(Plugin):
    def __init__(self, entity_id, api_key, logger, args = None):
        super().__init__(entity_id, api_key)
        self.logger = logger
        self.mongo = MongoClient(settings.MONGODB_URI)
        self.db = self.mongo[settings.MONGO_DBNAME].hpit_skills
        
        """
        try:
            self.cache = Couchbase.connect(bucket = "skill_cache", host = settings.COUCHBASE_HOSTNAME)
        except couchbase.exceptions.BucketNotFoundError:
            options = {
                "authType":"sasl",
                "saslPassword":"",
                "bucketType":"memcached",
                "flushEnabled":1,
                "name":"skill_cache",
                "ramQuotaMB":100,
            }
            req = requests.post(settings.COUCHBASE_BUCKET_URI,auth=settings.COUCHBASE_AUTH, data = options)
            
            self.cache = Couchbase.connect(bucket = "skill_cache", host = settings.COUCHBASE_HOSTNAME)
        """
     
    def post_connect(self):
        super().post_connect()
        
        self.subscribe({
            "tutorgen.get_skill_name":self.get_skill_name_callback,
            "tutorgen.get_skill_id":self.get_skill_id_callback,
            "tutorgen.skill_transaction":self.transaction_callback_method})
        
        #self.register_transaction_callback(self.transaction_callback_method)

    #Skill Management Plugin
    def get_skill_name_callback(self, message):
        if self.logger:
            self.send_log_entry("GET_NAME")
            self.send_log_entry(message)
            
        try:
            skill_id = ObjectId(message["skill_id"])
        except KeyError:
            self.send_response(message["message_id"],{
                "error":"Message must contain a 'skill_id'",       
            })
            return
        except bson.errors.InvalidId:
            self.send_response(message["message_id"],{
                "error":"'skill_id' is not a valid ObjectId",       
            })
            return
        
        skill = self.db.find_one({"_id":ObjectId(str(skill_id))})
        if not skill:
            self.send_response(message["message_id"],{
                "error":"Skill with id " + str(skill_id) + " does not exist.",     
            })
            return
            
        else:
            self.send_response(message["message_id"],{
                "skill_name":str(skill["skill_name"]),
                "skill_id":str(skill["_id"])
            })

    def get_skill_id_callback(self, message):
        if self.logger:
            self.send_log_entry("GET_ID")
            self.send_log_entry(message)
            
        try:
            skill_name = message["skill_name"]
        except KeyError:
            self.send_response(message["message_id"],{
                "error":"Message must contain a 'skill_name'",      
            })
            return
        
        if "skill_model" not in message:
            skill_model = "Default"
        else:
            skill_model = str(message["skill_model"])
        
        """
        try:
            cached_skill = self.cache.get(skill_model+skill_name)
            skill_id = cached_skill.value
            self.send_response(message["message_id"],{
                "skill_name": skill_name,
                "skill_model":skill_model,
                "skill_id": str(skill_id),
                "cached":True
            })
            return
        except couchbase.exceptions.NotFoundError:
            cached_skill = None
        """
        
        skill = self.db.find_one({"skill_name":skill_name,"skill_model":skill_model})
        if not skill:
            skill_id = self.db.insert({"skill_name":skill_name,"skill_model":skill_model})
            self.send_response(message["message_id"],{
                "skill_name": skill_name,
                "skill_model":skill_model,
                "skill_id": str(skill_id),
                "cached":False
            })
        else:
            self.send_response(message["message_id"],{
                "skill_name": skill_name,
                "skill_model":skill_model,
                "skill_id": str(skill["_id"]),
                "cached":False
            })
        #self.cache.set(str(skill_model+skill_name),str(skill_id))      
        
    def transaction_callback_method(self,message):
        if self.logger:
            self.send_log_entry("RECV: transaction with message: " + str(message))

        try:
            sender_entity_id = message["sender_entity_id"]
            skill_ids = dict(message["skill_ids"])
        except KeyError:
            self.send_response(message['message_id'],{"error":"transaction for Skill Manager requires 'skill_ids'","responder":["skill_manager"],})
            return
        except (TypeError, ValueError):
            self.send_response(message["message_id"],{
                    "error" : "The supplied 'skill_ids' is not valid; must be dict.",
                    "responder":["skill_manager"],
            })
            return
            
        if len(skill_ids)<1:
            self.send_response(message["message_id"],{
                    "error" : "The supplied 'skill_ids' is empty.",
                    "responder":["skill_manager"],
            })
            return
            
        for skill_name, skill_id in skill_ids.items():
            try:
                skill = self.db.find_one({"skill_name":skill_name,"_id":ObjectId(str(skill_id))})
            except bson.errors.InvalidId:
                self.send_response(message["message_id"],{
                    "error" : "Skill " + str(skill_name) + " is not paired with a valid id.",
                    "responder":["skill_manager"],
                })
                return
                
            if not skill:
                self.send_response(message["message_id"],{
                    "error" : "Skill " + str(skill_name) + " was not found, try adding it with get_skill_id.",
                    "responder":["skill_manager"],
                })
                return

        def next_step_callback(response):
            for k,v, in skill_ids.items():
                skill_ids[k] = str(v)
            response["skill_ids"] = skill_ids
            response["responder"] = ["skill_manager"] + response["responder"]
            self.send_response(message["message_id"],response)
            
        self.send("tutorgen.kt_transaction",message,next_step_callback)
        
                
