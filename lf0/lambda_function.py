"""LF0 - API Gateway -> Lex bridge. Use Lambda *proxy* integration on POST /chat.
Env vars: BOT_ID, BOT_ALIAS_ID, LOCALE_ID (default en_US)
IAM: lex:RecognizeText on your bot alias."""
import json, os, uuid, datetime
import boto3

lex = boto3.client('lexv2-runtime')
BOT_ID = os.environ['BOT_ID']
BOT_ALIAS_ID = os.environ['BOT_ALIAS_ID']
LOCALE_ID = os.environ.get('LOCALE_ID', 'en_US')

CORS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': '*',
    'Access-Control-Allow-Methods': 'OPTIONS,POST',
    'Content-Type': 'application/json',
}

def _reply(status, text):
    body = {'messages': [{
        'type': 'unstructured',
        'unstructured': {
            'id': str(uuid.uuid4()),
            'text': text,
            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
        }}]}
    return {'statusCode': status, 'headers': CORS, 'body': json.dumps(body)}

def lambda_handler(event, context):
    try:
        body = event.get('body', event)
        if isinstance(body, str):
            body = json.loads(body)
        text = body['messages'][0]['unstructured']['text']
    except Exception:
        return _reply(400, 'Bad request: expected messages[0].unstructured.text')

    # Boilerplate version (assignment part 2C) - use this first, then switch to the Lex call below (part 4)
    return _reply(200, "I'm still under development. Please come back later.")

    session_id = body.get('sessionId') or 'default-session'  # frontend sends its own per-user id
    try:
        r = lex.recognize_text(botId=BOT_ID, botAliasId=BOT_ALIAS_ID,
                               localeId=LOCALE_ID, sessionId=session_id, text=text)
        msgs = r.get('messages', [])
        reply = ' '.join(m['content'] for m in msgs) if msgs else "Sorry, I didn't catch that."
        return _reply(200, reply)
    except Exception as e:
        print('Lex error:', e)
        return _reply(500, 'Something went wrong talking to the bot.')
