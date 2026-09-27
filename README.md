# CorporateMapper

CorporateMapper is a defensive cybersecurity / OSINT platform intended to map an organisation's publicly avaliable attack surface. The idea being to allow a company to easily see where they are most at risk in terms of phishing, **the most common attack vector**.  


# Disclaimer 

Because this is holding sensitive personal information (eventhough it is public ...). We have made a demo demonsrating the working proof of concept ommiting real person information.


# How to set-up and use

## Set up

To set up this project simply run

docker compose up -d
python -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install --prefix frontend
npm run build --prefix frontend

set -a; source .env; set +a
.venv/bin/python app/demo.py --refresh
.venv/bin/python app/enrich.py --demo

.venv/bin/python -m uvicorn api:app --app-dir app --host 127.0.0.1 --port 8000

Then open http://127.0.0.1:8000 in your browser. Keep that last command running.

## How to use

To test it on real company simply add the url of the company to the top search bar.

Then wait as we crawling and scrap for any personal information we can find.

Then just select your organisation and look at who we found.

Click on the employee too see some more data (will work in the demo not in the real example)

look at the risk score and don't phish them



# AI USAGE

We did use AI throughout this project. 

## Parts that were all us no AI:

Phishing risk research
    - Finding all of the relevant factors that makes someone at risk to phising and adding a score next to it

Idea generation 

Archtectural planning

Tech stack

## Parts that was a mix of real and AI:

inital scraping code

most scripts


## Parts that were mostly AI:

front-end 

back-end neo4j inserts

a lot of other stuff 

testing files - all ai