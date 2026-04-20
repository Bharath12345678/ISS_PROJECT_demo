[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/rd3t__9M)
# Introduction to Software Systems S26 
## Course Project: Identity-Verified Multiplayer Arena

The assignment is available [here](https://cs6201.github.io/s26/assets/Project.pdf).

[This](https://hackmd.io/@iss-spring-2026/S1WBWzzoWe) is where you can ask questions about it, for which you will receive answers [here](https://hackmd.io/@iss-spring-2026/ryZ_WGzibx).

Good luck, have fun!


#Phase 1

##Schema for MySQL:
uid VARCHAR(255) PRIMARY KEY
name VARCHAR(255)
elo_rating INT DEFAULT 1200
is_online BOOLEAN DEFAULT FALSE

##MongoDB: Collection profile_images stores scraped profile images keyed by uid. 
Each document contains uid (string) and image (binary data).

##Command to run:
uv run python scraper.py

##Notes:
website_url in csv file is missing http so it was added manually.

#Phase 2

##Notes:
style.css was ai generated for aesthetic purposes. User is redirected to a placeholder lobby after successful login (for now).