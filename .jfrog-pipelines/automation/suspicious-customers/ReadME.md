get-pipelines-yaml.sh

* Login to SDM to access the kubernetes cluster
* install narc_cli using the wiki `https://jfrog-int.atlassian.net/wiki/spaces/PROD/pages/93257747/Narcissus+Golang+CLI`
* Run `export JFROG_SERVER_ENVIRONMENT=production` and `export NARCISSUS_TOKEN=<Token>` in your terminal
(Note - NARCISSUS_TOKEN can be generated from the UI, profiles -> Generated Token)
* Add a file with server names, separated by new-line
* `bash get-pipelines-yaml.sh <newly-created-file>` - This will add pipelines yaml JSONs with the server as filenames

