docker-compose -f docker-compose-test.yml --env-file=ops/env/test.env up --build --abort-on-container-exit --exit-code-from app --force-recreate
