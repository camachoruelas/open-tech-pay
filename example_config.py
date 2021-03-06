SQLALCHEMY_DATABASE_URI = 'postgresql://user:password@localhost/databasename'
SQLALCHEMY_TRACK_MODIFICATIONS = False
SERVER_NAME = 'localhost:5000' # Used by url_for()

#Mailjet
MAILJET_API_KEY = ''
MAILJET_API_SECRET = ''

# Used on the frontend for this particular deployment
DEPLOYMENT_NAME = 'OpenPay'
REGION_NAME = 'Region'

# A List of string messages
MESSAGES = []

# Other settings
MARKET_DATA_MIN_DISPLAY = 4
RANDOMIZE_MARKET_DATA = False