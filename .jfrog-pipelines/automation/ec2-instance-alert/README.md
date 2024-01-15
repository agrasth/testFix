Requirements for orphaned-nodes-manual-check

* install postgresql14 `brew install postgresql`
* install libpq: `brew install libpq`
* install requirements: `pip3 install -r requirements.txt`
* run the command to login to AWS for the role: `EC2_ReadOnlyAccess` in the account: `jfrog-pipelines-cloud-prod (4216-2073-7690)`
* Add the credentials.json file to the same folder (See note `credentials for running orphaned-nodes-manual-check.py`) in 1password
* Connect to the database: `sdm connect regular-user-AWS-psql-prod-euc-1-pipelines-repo21-dedicated-1-replica`
* Run the command: `python3 <path-tofile> --environment "PROD" --tag-key "Customer Name" --tag-value "jfrogrepo21" --db-name 'jfrogrepo21_jfpl' --db-user 'jfrogrepo21_jfpl' --db-password '<password>' --db-host localhost --db-port 10022`
----
* DB calls are moved to API, uncomment the DB-call code, and comment out `instances_to_delete = filter_orphaned_instances()` to run with DB checks
* Run the command: `python3 orphaned-nodes-prod-check.py.py --environment "PROD" --tag-key "Customer Name" --tag-value "jfrogrepo21" --jpd-endpoint "https://entplus.jfrog.io" --jpd-user-access-token "<USER-ACCESS_TOKEN>"`

Errors:
* NoCredentialsError
```
File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/botocore/auth.py", line 418, in add_auth
    raise NoCredentialsError()
```
    * Run the commands to login to AWS
