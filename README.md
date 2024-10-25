# mescapes

1. Do the standard Python virtual environment setup:

   python3 -m venv env
   env/bin/activate

   pip install -r requirements.lock

2. Then get a token from your Dirigera hub:

   env/bin/generate-token

3. Run

   python main.py scenes/welcome.json

## Debugging

        % curl -H "Authorization: Bearer <token>" --request PATCH --data '[{"attributes": {"lightLevel": 47.77165354330709}, "transitionTime": 10}]' -H "content-type: application/json" --insecure https://<ip_address>>:8443/v1/devices/<id>
