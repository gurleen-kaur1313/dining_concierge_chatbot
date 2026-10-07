"""LF2 - queue worker: SQS -> OpenSearch -> DynamoDB -> SES.
Env vars: QUEUE_URL, OS_ENDPOINT (https://search-xxx.us-east-1.es.amazonaws.com),
          OS_USER, OS_PASS, SENDER (SES-verified email)
Optional: TABLE (yelp-restaurants), STATE_TABLE (user-state)
IAM: sqs:ReceiveMessage/DeleteMessage, dynamodb:GetItem/UpdateItem, ses:SendEmail.
Timeout: set to ~30s."""
import json, os, base64, urllib.request
import boto3

sqs = boto3.client('sqs')
ses = boto3.client('ses')
ddb = boto3.resource('dynamodb')
QUEUE_URL = os.environ['QUEUE_URL']
OS_ENDPOINT = os.environ['OS_ENDPOINT'].rstrip('/')
AUTH = 'Basic ' + base64.b64encode(f"{os.environ['OS_USER']}:{os.environ['OS_PASS']}".encode()).decode()
SENDER = os.environ['SENDER']
rest_table = ddb.Table(os.environ.get('TABLE', 'yelp-restaurants'))
state_table = ddb.Table(os.environ.get('STATE_TABLE', 'user-state'))


def random_ids(cuisine, n=3):
    q = {'size': n, 'query': {'function_score': {
        'query': {'match': {'Cuisine': cuisine}}, 'random_score': {}}}}
    req = urllib.request.Request(
        f'{OS_ENDPOINT}/restaurants/_search', data=json.dumps(q).encode(), method='POST',
        headers={'Content-Type': 'application/json', 'Authorization': AUTH})
    with urllib.request.urlopen(req, timeout=10) as r:
        hits = json.loads(r.read())['hits']['hits']
    return [h['_source']['RestaurantID'] for h in hits]


def lookup(ids):
    out = []
    for i in ids:
        item = rest_table.get_item(Key={'business_id': i}).get('Item')
        if item:
            out.append(item)
    return out


def handle(body):
    cuisine, email = body['Cuisine'], body['Email']
    ids = None
    if body.get('repeat'):  # extra credit: reuse last recommendation
        prev = state_table.get_item(Key={'email': email}).get('Item') or {}
        ids = prev.get('restaurantIds')
    if not ids:
        ids = random_ids(cuisine)
    restaurants = lookup(ids)
    if not restaurants:
        raise RuntimeError('no restaurants found')
    state_table.update_item(Key={'email': email},
        UpdateExpression='SET restaurantIds = :r', ExpressionAttributeValues={':r': ids})

    lines = [f"{n}. {r['name']}, located at {r['address']}" for n, r in enumerate(restaurants, 1)]
    text = (f"Hello! Here are my {cuisine.capitalize()} restaurant suggestions for "
            f"{body['NumberOfPeople']} people, for today at {body['DiningTime']}:\n\n"
            + '\n'.join(lines) + '\n\nEnjoy your meal!')
    ses.send_email(Source=SENDER, Destination={'ToAddresses': [email]},
                   Message={'Subject': {'Data': f'Your {cuisine.capitalize()} dining suggestions'},
                            'Body': {'Text': {'Data': text}}})


def lambda_handler(event, context):
    resp = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=5, WaitTimeSeconds=2)
    for m in resp.get('Messages', []):
        try:
            handle(json.loads(m['Body']))
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=m['ReceiptHandle'])
        except Exception as e:
            print('failed:', e, m['Body'])  # stays on queue; retried after visibility timeout
    return {'processed': len(resp.get('Messages', []))}
