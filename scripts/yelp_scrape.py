"""Scrape >=1000 unique Manhattan restaurants from Yelp into DynamoDB 'yelp-restaurants'.
Run locally:  pip install requests boto3 ; aws configure ; export YELP_API_KEY=...
python yelp_scrape.py"""
import os, time, datetime, requests, boto3
from decimal import Decimal

API_KEY = os.environ['YELP_API_KEY']
REGION = os.environ.get('AWS_REGION', 'us-east-1')
CUISINES = ['chinese', 'japanese', 'italian', 'mexican', 'indian', 'thai', 'french', 'korean']
PER_CUISINE = 200          # 4 pages x 50 (Yelp caps results at ~240 per query)

ddb = boto3.resource('dynamodb', region_name=REGION)

def ensure_table():
    client = boto3.client('dynamodb', region_name=REGION)
    if 'yelp-restaurants' not in client.list_tables()['TableNames']:
        client.create_table(TableName='yelp-restaurants',
            AttributeDefinitions=[{'AttributeName': 'business_id', 'AttributeType': 'S'}],
            KeySchema=[{'AttributeName': 'business_id', 'KeyType': 'HASH'}],
            BillingMode='PAY_PER_REQUEST')
        client.get_waiter('table_exists').wait(TableName='yelp-restaurants')
    return ddb.Table('yelp-restaurants')

def fetch(cuisine, offset):
    r = requests.get('https://api.yelp.com/v3/businesses/search',
        headers={'Authorization': f'Bearer {API_KEY}'},
        params={'term': f'{cuisine} restaurants', 'location': 'Manhattan',
                'limit': 50, 'offset': offset}, timeout=15)
    r.raise_for_status()
    return r.json().get('businesses', [])

def main():
    table = ensure_table()
    seen = set()
    for cuisine in CUISINES:
        count = 0
        for offset in range(0, PER_CUISINE, 50):
            for b in fetch(cuisine, offset):
                if b['id'] in seen:
                    continue
                seen.add(b['id'])
                loc = b.get('location', {})
                coords = b.get('coordinates') or {}
                table.put_item(Item={
                    'business_id': b['id'],
                    'name': b['name'],
                    'address': ', '.join(loc.get('display_address', [])),
                    'coordinates': {'latitude': Decimal(str(coords.get('latitude') or 0)),
                                    'longitude': Decimal(str(coords.get('longitude') or 0))},
                    'review_count': b.get('review_count', 0),
                    'rating': Decimal(str(b.get('rating', 0))),
                    'zip_code': loc.get('zip_code', ''),
                    'cuisine': cuisine,
                    'insertedAtTimestamp': datetime.datetime.utcnow().isoformat(),
                })
                count += 1
            time.sleep(0.3)
        print(f'{cuisine}: {count} new')
    print('total unique:', len(seen))

if __name__ == '__main__':
    main()