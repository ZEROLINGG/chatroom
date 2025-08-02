import json
import uuid

from app.utils.eec import Eec

k = {
    "uuid": str(uuid.uuid4()),
    "key_type": "qq",
    "qq_number": 222222222,
    "ttl": 47474747744747474
}
json_k = json.dumps(k)
d = Eec.Aes.Cbc.encrypt_str(json_k, "1111111111111111")
print(d)
print(len(d))
