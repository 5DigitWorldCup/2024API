#!/bin/bash
docker run -d -p 5432:5432 --name 5wc2024-db-test -e POSTGRES_PASSWORD=postgres -v 5wc2024db-test:/var/lib/postgresql postgres