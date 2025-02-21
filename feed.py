from atproto import Client
from pprint import pprint
from dotenv import load_dotenv
import os
import sqlite3
import shortuuid
import datetime
import boto3
import pytz
from botocore.exceptions import ClientError
from xml.etree.ElementTree import fromstring
from feedgen.feed import FeedGenerator

def bsClient(login, password):
  client = Client()
  client.login(login, password)
  #print(client)
  return client

def bsFeed(client, feedId):
  data = client.app.bsky.feed.get_feed({
    'feed': feedId, #https://bsky.app/profile/davidsacerdote.bsky.social/feed/aaaixbb5liqbu
    'limit': 100,
  }, headers={'Accept-Language': 'en'})

  feed = data.feed
  
  # write feed to file for debug
  #with open("Output.txt", "w") as text_file:
  #  print(f"debug output \n{feed}", file=text_file)
  #
    
  return feed

def bsItems(feed):
  #gifts = []
  for item in feed: 
    try:
      p = item.post
      r = item.post.record
      
      handle = p.author.handle
      author = p.author.display_name
      social = (item.post.like_count + item.post.repost_count)
      date = r.created_at
      post = r.text if r.text else ''
      url = p.embed.images[0].fullsize
      #print (f"\n\nauthor => ({handle}) {author}")
      #print (f"social => {social}")
      #print (f"posted => {date}")
      #print (f"post text => {post}")
      #print (f"meme url => {url}")
          
      dbAdd(author, post, url, date, social)
    except AttributeError:
      pass
    except sqlite3.IntegrityError as e:
      print(e)    
    except Exception as e:
      #print(f"Error processing embed: {e}")
      pass

def dbInit():
  try:
    with sqlite3.connect(dbFile) as conn:
      conn.execute("""
        CREATE TABLE feed (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          author TEXT NOT NULL,
          post TEXT NOT NULL,
          url TEXT NOT NULL UNIQUE,
          date DATE NOT NULL,
          social int NOT NULL
        )
      """)
  except sqlite3.OperationalError as e:
    print("-",e)

def dbAdd(author, post, url, date, social):
  try:
    if url:
      with sqlite3.connect(dbFile) as conn:
        conn.execute("INSERT INTO feed (author, post, url, date, social) VALUES (?, ?, ?, ?, ?)", (author, post, url, date, social))
        print("* Added: ", post, url, social)
  except (sqlite3.OperationalError, sqlite3.IntegrityError) as e:
    #print("Failed to insert item:", e)
    pass

def buildRSS(dbFile):
  try:
    with sqlite3.connect(dbFile) as conn:
      name = "all"
      cursor = conn.cursor()
      query = "SELECT id, author, post, url, date AS day FROM feed ORDER BY date DESC"
      #query = "SELECT id, author, post, url, date AS day FROM feed WHERE social > 0 ORDER BY date DESC"

      cursor.execute(query)      
      #query = "SELECT * FROM feed ORDER BY date DESC"
      rows = cursor.fetchall()
      
      fg = FeedGenerator()
      fg.id('http://nealshyam.com/rss/meme.rss')
      fg.title('Bluesky Memes')
      fg.author( {'name':'Neal Shyam','email':'nealrs+rss@gmail.com'} )
      fg.link( href='http://nealshyam.com/rss/meme.rss', rel='alternate' )
      #fg.logo('http://ex.com/logo.jpg')
      fg.subtitle('A RSS feed of memes from BlueSky. Updated every 20 minutes.')
      fg.description('A RSS feed of memes from BlueSky. Updated every 20 minutes.')
      fg.link( href='http://nealshyam.com/rss/meme.rss', rel='self' )
      fg.language('en')
      
      for row in rows:
        fe = fg.add_entry()
        fe.id(row[3])
        fe.guid(row[3])
        fe.author( {'name':row[1],'email':row[1]} )
        fe.title(row[1])
        fe.link(href=f'{row[3]}')
        fe.enclosure(row[3], 0, 'image/jpeg')
        stripped = row[2].replace("\n", " ")
        fe.content(content=f'<p>{stripped}</p> <img src="{row[3]}">', src=None, type="CDATA")
        
        try:
          fe.pubDate(datetime.datetime.strptime(row[4], '%Y-%m-%dT%H:%M:%S.%fZ').astimezone(pytz.timezone('UTC')).strftime('%a, %d %b %Y %H:%M:%S %z'))
        except ValueError as e:
          print(e)
          fe.pubDate(datetime.datetime.now().astimezone(pytz.timezone('UTC')).strftime('%a, %d %b %Y %H:%M:%S %z'))
          #2025-02-09T01:15:06.490817+00:00

      rss  = fg.rss_str(pretty=True) # Get the RSS feed as string
      fg.rss_file('meme.rss') # Write the RSS feed to a file
      return rss
  except sqlite3.OperationalError as e:
    print("Failed to fetch items:", e)
    return []

def writeRSS(rss):
  try:
    #s3 = boto3.resource("s3")
    s3 = boto3.client('s3', aws_access_key_id=aws_key, aws_secret_access_key=aws_secret)
    #print("Connected to s3!!")
    
    s3.put_object(
      Bucket=bucket,
      Key="rss/meme.rss",
      Body=rss,
      ACL="public-read",
      ContentType="application/rss+xml"
    )
    print("- wrote meme.rss to s3")
    return True
  except Exception as e:
      print("^error writing meme.rss to s3")
      raise
      return

def updateHTML(rss):
  html = """
    <html>
    <head>
        <title>RSS Meme feed from Bluesky</title>
        <meta name="robots" content="noindex, nofollow">
        <meta name="description" content="We all need to laugh">
        <meta property="og:title" content="Memes from Bluesky">
        <meta property="og:description" content="We all need to laugh">
        <meta property="og:type" content="website">
        <meta name="author" content="Neal Shyam | @nealrs">
        <link rel="canonical" href="https://nealshyam.com/rss/meme.html">
        <meta property="og:url" content="https://nealshyam.com/rss/meme.html">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <styles>
        <style>
          body {
            max-width: 80%;
            margin: 0 auto;
            text-align: left;
            font-size: 1.3rem;
            color: 111111;
            background-color: #fffdf5;
          }
          h1, h3{
            color: #38220f;
          }

          a {color: #38220f;}
          a:active, a:hover {color: #967259;}
          table {
            max-width: 70%;
            border-collapse: collapse;
          }
          th, td {
            border: 1px solid #ddd;
            padding: 8px;
            font-size: 1rem;
          }
          th {
            background-color: #f2f2f2;
            text-align: left;
          }
          
          .list{
            font-size: 1rem;
          }
          img {
            max-width: 300px;
          }
        </style>
    </head>
    <body>
      <div>
        <h2>RSS Feed of Memes</h2>
        <p>I converted <a href="hhttps://bsky.app/profile/jakei.bsky.social" target="_blank">Jake I's</a> Bluesky <a href="https://bsky.app/profile/jakei.bsky.social/feed/aaaklnttvaage" target="_blank">Meme feed</a> into an RSS feed.</p>
        
        <p>More info & code at <a href="https://github.com/nealrs/bluememe">github</a>.</p>
        
        <p>Last update: <span id="last-updated"></span></p>

        <h3><a href="./meme.rss" target="_blank">RSS Feed</a></h3>
        <div id="all"></div>

        <hr>
        <p>&copy; <a href="https://nealshyam.com" target="_blank">Neal Shyam</a></p>      
      </div>
    </body>
    </html>
  """
  
  if rss:
    rss_xml = fromstring(rss)
    items = rss_xml.findall('.//item')[:10]
    list_items = ''.join(f'<p> {item.find("pubDate").text} <a href="{item.find("link").text}">{item.find("author").text}</a></p><p>{item.find("description").text}</p>' for item in items)
    html = html.replace('<div id="all"></div>', f'<div id="all">{list_items}</div>')
  
  current_time = datetime.datetime.now().astimezone(pytz.timezone('US/Eastern')).strftime('%I:%M %p, %m/%d/%y')
  html = html.replace('<span id="last-updated"></span>', f'<span id="last-updated">{current_time}</span>')

  try:
    s3 = boto3.client('s3', aws_access_key_id=aws_key, aws_secret_access_key=aws_secret)
    #print("Connected to s3!!")
    s3.put_object(
      Bucket=bucket,
      Key="rss/meme.html",
      Body=html,
      ACL="public-read",
      ContentType="text/html"
    )
    print("- wrote html to s3")
    return True
  except Exception as e:
      print("^error writing html to s3")
      raise
      return
    
# OK LET'S DO THIS
print('\n*****************')
print(datetime.datetime.now().astimezone(pytz.timezone('US/Eastern')).strftime('%A, %d-%m-%Y, %I:%M %p %Z'))

## load env vars &setup
load_dotenv()
feedId = os.getenv('feedId')
login = os.getenv('login')
password = os.getenv('password')
dbFile = os.getenv('dbFile')
aws_key = os.getenv('aws_access_key_id')
aws_secret = os.getenv('aws_secret_access_key')
bucket = os.getenv('bucket')
folder='rss/'

## create db & update it with new items
dbInit() # initialize the database & table if it doesen't e  print (blacklist)st    
client = bsClient(login, password) # login to bluesky
feed = bsFeed(client, feedId) # get all feed items
bsItems(feed) # process & insert feed items.
#print(feed)

## build feeds from db & save it to s3
rss = buildRSS(dbFile) # build the RSS feed
#print(rss)

writeRSS(rss)
updateHTML(rss)

print('*****************\n')