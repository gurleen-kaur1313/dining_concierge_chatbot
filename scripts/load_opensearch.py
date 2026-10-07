"""Copy RestaurantID + Cuisine from DynamoDB into OpenSearch index 'restaurants'.
Run last (OpenSearch costs money while running).
export OS_ENDPOINT=https://search-xxx.us-east-1.es.amazonaws.com OS_USER=master OS_PASS=...
"""
import os, json, base64, urllib.request, boto3

ENDPOINT = os.environ['OS_ENDPOINT'].rstrip('/')
AUTH = 'Basic ' + base64.b64encode(f"{os.environ['OS_USER']}:{os.environ['OS_PASS']}".encode()).decode()
table = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1')).Table('yelp-restaurants')

def call(path, data, ctype='application/json'):
    req = urllib.request.Request(ENDPOINT + path, data=data.encode(), method='POST',
                                 headers={'Content-Type': ctype, 'Authorization': AUTH})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

items, kw = [], {}
while True:
    page = table.scan(ProjectionExpression='business_id, cuisine', **kw)
    items += page['Items']
    if 'LastEvaluatedKey' not in page:
        break
    kw['ExclusiveStartKey'] = page['LastEvaluatedKey']

lines = []
for it in items:
    lines.append(json.dumps({'index': {'_index': 'restaurants', '_id': it['business_id']}}))
    lines.append(json.dumps({'RestaurantID': it['business_id'], 'Cuisine': it['cuisine']}))
res = call('/_bulk', '\n'.join(lines) + '\n', ctype='application/x-ndjson')
print('indexed', len(items), 'errors:', res.get('errors'))
print(call('/restaurants/_search', json.dumps({'size': 2, 'query': {'match': {'Cuisine': 'italian'}}})))