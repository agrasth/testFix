#!/bin/bash

counter=1

# Loop through each server name in the text file
while IFS= read -r server; do
    # Perform actions for each server, with a numbered prefix

    echo "Processing server $counter: $server"

    region=$(narc_cli getCustomerDetails -c "$server" | jq '.region' | tr -d '"')

    cluster=$(kubectx | grep $region | head -n 1)

    kubectx $cluster


    secret=$(kubectl get secrets pipelines-unified-secret -o json -n $server | jq '.data."system.yaml"' | tr -d '"')

    auth=$(echo -n $secret | base64 -d | grep "installerAuthToken" | awk '{print $2}' | tr -d '"')

    curl -H "authorization: apiToken $auth" https://$server.jfrog.io/pipelines/api/v1/pipelines -vk > $server.json

    echo "Run to get the JSON - curl -H \"authorization: apiToken $auth\" https://$server.jfrog.io/pipelines/api/v1/pipelines -vk > $server.json"
    
    
    ((counter++))
done < $1