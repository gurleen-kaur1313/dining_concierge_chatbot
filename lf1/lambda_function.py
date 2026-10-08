"""LF1 - Lex V2 code hook (dialog validation + fulfillment).
Env vars: QUEUE_URL, STATE_TABLE (default user-state)
IAM: sqs:SendMessage on Q1, dynamodb:GetItem/PutItem on user-state."""
import json, os, re, boto3, datetime

sqs = boto3.client('sqs')
ddb = boto3.resource('dynamodb')
QUEUE_URL = os.environ['QUEUE_URL']
STATE_TABLE = os.environ.get('STATE_TABLE', 'user-state')

CUISINES = {'chinese', 'japanese', 'italian', 'mexican', 'indian', 'thai', 'french', 'korean'}
LOCATIONS = {'manhattan', 'new york', 'new york city', 'nyc'}
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
REQUIRED = ['Location', 'Cuisine', 'DiningTime', 'NumberOfPeople', 'Email']


# ---------- helpers ----------
def val(slots, name):
    s = (slots or {}).get(name)
    if s and s.get('value'):
        return s['value'].get('interpretedValue')
    return None

def build(intent, attrs, action, message=None, state=None):
    if state:
        intent['state'] = state
    r = {'sessionState': {'sessionAttributes': attrs, 'dialogAction': action, 'intent': intent}}
    if message:
        r['messages'] = [{'contentType': 'PlainText', 'content': message}]
    return r

def delegate(intent, attrs):
    return build(intent, attrs, {'type': 'Delegate'})

def close(intent, attrs, message):
    return build(intent, attrs, {'type': 'Close'}, message, 'Fulfilled')

def elicit(intent, attrs, slot, message):
    intent['slots'][slot] = None
    return build(intent, attrs, {'type': 'ElicitSlot', 'slotToElicit': slot}, message)

def confirm(intent, attrs, message):
    return build(intent, attrs, {'type': 'ConfirmIntent'}, message)


# ---------- validation ----------
def validate(slots):
    """returns (slot, message) for first invalid slot, or None"""
    loc = val(slots, 'Location')
    if loc and loc.strip().lower() not in LOCATIONS:
        return 'Location', f"Sorry, I can't fulfill requests for {loc}. Please enter a valid location (e.g. Manhattan)."
    cuisine = val(slots, 'Cuisine')
    if cuisine and cuisine.strip().lower() not in CUISINES:
        return 'Cuisine', f"Sorry, I don't have {cuisine}. Try one of: {', '.join(sorted(CUISINES))}."
    n = val(slots, 'NumberOfPeople')
    if n:
        try:
            if not 1 <= int(float(n)) <= 20:
                raise ValueError
        except ValueError:
            return 'NumberOfPeople', 'Please give me a party size between 1 and 20.'
    email = val(slots, 'Email')
    if email and not EMAIL_RE.match(email):
        return 'Email', "That email doesn't look right. Could you re-enter it?"
    return None


# ---------- extra credit: remember last search ----------
def get_prev(email):
    try:
        return ddb.Table(STATE_TABLE).get_item(Key={'email': email}).get('Item')
    except Exception as e:
        print('state read error', e)
        return None

def is_same(prev, loc, cuisine):
    # LF2 may have created the row with only restaurantIds, so fields can be missing
    return bool(prev and prev.get('location') == loc.lower() and prev.get('cuisine') == cuisine.lower())

def save_state(email, loc, cuisine):
    # update (not put) so LF2's restaurantIds survive for the repeat feature
    try:
        ddb.Table(STATE_TABLE).update_item(Key={'email': email},
            UpdateExpression='SET #l = :l, cuisine = :c, updatedAt = :t',
            ExpressionAttributeNames={'#l': 'location'},
            ExpressionAttributeValues={':l': loc.lower(), ':c': cuisine.lower(),
                                       ':t': datetime.datetime.utcnow().isoformat()})
    except Exception as e:
        print('state write error', e)


# ---------- intents ----------
def dining(event):
    src = event['invocationSource']
    intent = event['sessionState']['intent']
    attrs = event['sessionState'].get('sessionAttributes') or {}
    slots = intent['slots']

    def _fulfill():
        loc, cuisine = val(slots, 'Location'), val(slots, 'Cuisine')
        email = val(slots, 'Email')
        prev = get_prev(email)
        repeat = is_same(prev, loc, cuisine)
        msg = {
            'Location': loc, 'Cuisine': cuisine.lower(),
            'DiningTime': val(slots, 'DiningTime'),
            'NumberOfPeople': val(slots, 'NumberOfPeople'),
            'Email': email, 'repeat': repeat,
        }
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(msg))
        save_state(email, loc, cuisine)
        return close(intent, attrs,
            "You're all set. Expect my suggestions by email shortly! Have a good day.")

    if src == 'DialogCodeHook':
        bad = validate(slots)
        if bad:
            return elicit(intent, attrs, bad[0], bad[1])
        if all(val(slots, s) for s in REQUIRED):
            loc, cuisine = val(slots, 'Location'), val(slots, 'Cuisine')
            email = val(slots, 'Email')
            prev = get_prev(email)
            same = is_same(prev, loc, cuisine)
            conf = intent.get('confirmationState', 'None')
            if same and conf == 'None':
                return confirm(intent, attrs,
                    f"Welcome back! Last time you searched {prev['cuisine']} in {prev['location']}. "
                    "Do you want the same recommendations as last time?")
            if same and conf == 'Denied':
                return close(intent, attrs, "No problem. Just start a new request whenever you like.")
            return _fulfill()
        return delegate(intent, attrs)

    # FulfillmentCodeHook fallback
    return _fulfill()


def lambda_handler(event, context):
    print(json.dumps(event))
    intent = event['sessionState']['intent']
    attrs = event['sessionState'].get('sessionAttributes') or {}
    name = intent['name']
    if name == 'GreetingIntent':
        return close(intent, attrs, 'Hi there, how can I help?')
    if name == 'ThankYouIntent':
        return close(intent, attrs, "You're welcome!")
    if name == 'DiningSuggestionsIntent':
        return dining(event)
    return close(intent, attrs, "Sorry, I didn't get that.")
