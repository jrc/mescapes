# mescapes

1.  Do the standard Python virtual environment setup:

        python3 -m venv env
        env/bin/activate

        pip install -r requirements.lock

2.  Then get a token from your Dirigera hub:

        env/bin/generate-token

3.  Run

        python main.py scenes/welcome.json

## Debugging

    export .env

    curl -H "Authorization: Bearer $DIRIGERA_TOKEN" --insecure https://$DIRIGERA_IP_ADDRESS:8443/v1/devices/ | python -mjson.tool

    curl -H "Authorization: Bearer $DIRIGERA_TOKEN" --insecure https://$DIRIGERA_IP_ADDRESS:8443/v1/devices/<id> | python -mjson.tool

    curl -H "Authorization: Bearer $DIRIGERA_TOKEN" --request PATCH --data '[{"attributes": {"colorHue": 120.0, "colorSaturation": 1.0}, "transitionTime": 1000}]' -H "content-type: application/json" --insecure https://$DIRIGERA_IP_ADDRESS:8443/v1/devices/<id>
