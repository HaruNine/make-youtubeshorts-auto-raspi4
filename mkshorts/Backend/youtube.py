import os
import sys
import time
import random
import httplib2

from termcolor import colored
from oauth2client.file import Storage
from apiclient.discovery import build
from apiclient.errors import HttpError
from apiclient.http import MediaFileUpload
from oauth2client.tools import argparser, run_flow
from oauth2client.client import flow_from_clientsecrets

# Explicitly tell the underlying HTTP transport library not to retry, since
# we are handling retry logic ourselves.
httplib2.RETRIES = 1

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# Always retry when these exceptions are raised.
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError, httplib2.ServerNotFoundError)

# Always retry when an apiclient.errors.HttpError with one of these status
# codes is raised.
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret.
CLIENT_SECRETS_FILE = "/app/Backend/client_secret.json"

# This OAuth 2.0 access scope allows an application to upload files to the
# authenticated user's YouTube channel, but doesn't allow other types of access.
# YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube',
          'https://www.googleapis.com/auth/youtubepartner']
YOUTUBE_API_SERVICE_NAME = "youtube"  
YOUTUBE_API_VERSION = "v3"  

# This variable defines a message to display if the CLIENT_SECRETS_FILE is
# missing.
MISSING_CLIENT_SECRETS_MESSAGE = f"""
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:
  
{os.path.abspath(os.path.join(os.path.dirname(__file__), CLIENT_SECRETS_FILE))}

with information from the API Console
https://console.cloud.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
"""

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")  
  
  
def get_authenticated_service():
    """
    This method retrieves the YouTube service.

    Returns:
        any: The authenticated YouTube service.
    """
    flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
                                   scope=SCOPES,
                                   message=MISSING_CLIENT_SECRETS_MESSAGE)

    storage = Storage(f"{sys.argv[0]}-oauth2.json")
    credentials = storage.get()

    if credentials is None or credentials.invalid:
        flags = argparser.parse_args()
        credentials = run_flow(flow, storage, flags)

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                 http=credentials.authorize(httplib2.Http()))

def initialize_upload(youtube, options, config):
    """브랜드 계정 업로드 초기화"""
    body = {
        'snippet': {
            'title': options['title'],
            'description': options['description'],
            'tags': options['keywords'].split(",") if options['keywords'] else None,
            'categoryId': options['category'],
            'channelId': config['channel_id']  # 브랜드 채널 ID 사용
        },
        'status': {
            'privacyStatus': config['privacyStatus'],
            'madeForKids': False
        }
    }

    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload(options['file'], chunksize=-1, resumable=True)
    )
    return resumable_upload(insert_request)

def resumable_upload(insert_request: MediaFileUpload):
    """
    This method implements an exponential backoff strategy to resume a  
    failed upload.

    Args:
        insert_request (MediaFileUpload): The request to insert the video.

    Returns:
        response: The response from the upload process.
    """
    response = None
    error = None
    retry = 0
    while response is None:
        try:
            print(colored(" => Uploading file...", "magenta"))
            status, response = insert_request.next_chunk()
            if 'id' in response:
                print(f"Video id '{response['id']}' was successfully uploaded.")
                return response
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = f"A retriable HTTP error {e.resp.status} occurred:\n{e.content}"
            else:
                raise
        except RETRIABLE_EXCEPTIONS as e:
            error = f"A retriable error occurred: {e}"

        if error is not None:
            print(colored(error, "red"))
            retry += 1
            if retry > MAX_RETRIES:
                raise Exception("No longer attempting to retry.")

            max_sleep = 2 ** retry 
            sleep_seconds = random.random() * max_sleep
            print(colored(f" => Sleeping {sleep_seconds} seconds and then retrying...", "blue"))
            time.sleep(sleep_seconds)  
  
def upload_video(video_path, title, description, category, keywords, privacy_status):
    try:
        # Get the authenticated YouTube service
        youtube = get_authenticated_service()

        # Retrieve and print the channel ID for the authenticated user
        channels_response = youtube.channels().list(mine=True, part='id').execute()
        for channel in channels_response['items']:
            print(colored(f" => Channel ID: {channel['id']}", "blue"))

        # Initialize the upload process
        video_response = initialize_upload(youtube, {
            'file': video_path, # The path to the video file
            'title': title,
            'description': description,
            'category': category, 
            'keywords': keywords,
            'privacyStatus': privacy_status
        })
        return video_response # Return the response from the upload process
    except HttpError as e:
        print(colored(f"[-] An HTTP error {e.resp.status} occurred:\n{e.content}", "red"))
        if e.resp.status in [401, 403]:
            # Here you could refresh the credentials and retry the upload  
            youtube = get_authenticated_service() # This will prompt for re-authentication if necessary
            video_response = initialize_upload(youtube, {
                'file': video_path,
                'title': title,
                'description': description,
                'category': category,
                'keywords': keywords,
                'privacyStatus': privacy_status
            })
            return video_response
        else:
            raise e 
        
def get_brand_credentials(config):
    """브랜드 계정 전용 인증"""
    storage = Storage(config['credentials_path'])
    credentials = storage.get()
    
    if not credentials or credentials.invalid:
        flow = flow_from_clientsecrets(
            CLIENT_SECRETS_FILE,
            scope=SCOPES,
            redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )
        auth_url = flow.step1_get_authorize_url()
        print(f"브랜드 계정 인증 URL: {auth_url}")
        code = input("인증 코드 입력: ")
        credentials = flow.step2_exchange(code)
        storage.put(credentials)
        
    return credentials

def upload_video_brand(video_path, title, description, category, keywords, config):
    """브랜드 계정 전용 업로드 함수"""
    try:
        # 브랜드 계정 인증
        credentials = get_brand_credentials(config)
        youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                       http=credentials.authorize(httplib2.Http()))

        # 채널 확인
        channels = youtube.channels().list(
            id=config['channel_id'],
            part='snippet'
        ).execute()
        
        if not channels['items']:
            raise Exception(f"채널 {config['channel_id']} 접근 실패 또는 존재하지 않음")

        # 업로드 실행
        response = initialize_upload(youtube, {
            'file': video_path,
            'title': title,
            'description': description,
            'category': category,
            'keywords': keywords
        }, config)
        
        print(colored(f"[업로드 성공] Video ID: {response['id']}", "green"))
        return response

    except HttpError as e:
        print(colored(f"[HTTP 오류] {e.resp.status}: {e.content}", "red"))
        raise