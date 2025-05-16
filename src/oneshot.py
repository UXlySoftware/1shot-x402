import os

from uxly_1shot_client import AsyncClient

# its handy to set your API key and secret with environment variables so you only have to change them in one place (i.e. docker-compose.env)
API_KEY = os.getenv("ONESHOT_API_KEY")
API_SECRET = os.getenv("ONESHOT_API_SECRET")
BUSINESS_ID = os.getenv("ONESHOT_BUSINESS_ID") 

# import the the 1Shot API async client with your API key and secret from your 1Shot Org (https://docs.1shotapi.com/org-creation.html)  
# its handy to instantiate it in a single location and import the singleton where you need it  
# be sure to use the AsyncClient with asynchronous frameworks like FastAPI    
oneshot_client = AsyncClient(api_key=API_KEY, api_secret=API_SECRET)