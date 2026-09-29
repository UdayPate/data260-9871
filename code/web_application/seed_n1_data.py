"""
DATA-260 Homework 4 - Part 3: Seed 5,000 fixtures + 200 related
fixture_updates rows, using SEED for reproducibility.

HW5 Part 1.I note: `fixtures` now also has a NOT NULL unique
`fixture_code` and a NOT NULL `home_team_id` foreign key, so this script
assigns both. Codes continue from the highest FX-9871-##### already in
the table, and home teams are picked round-robin over the seeded teams,
so re-running stays reproducible and never collides.

Run with: python seed_n1_data.py
"""

import random

from sqlalchemy import func

from db import Base, engine, db_session_basede26
import models
from models import Fixture, FixtureUpdate, Team

SEED = 9871
NUM_FIXTURES = 5000
NUM_UPDATES = 200

TEAM_NAMES = [
    "Lions", "Tigers", "Warriors", "Strikers", "Falcons", "Titans",
    "Eagles", "Sharks", "Wolves", "Bears", "Hawks", "Panthers",
]
CITIES = ["Milpitas", "San Jose", "Fremont", "Santa Clara", "Sunnyvale", "Oakland"]
SPORTS = ["Soccer", "Basketball", "Volleyball", "Cricket"]


def main():
    random.seed(SEED)
    Base.metadata.create_all(bind=engine)

    db = db_session_basede26()
    try:
        existing = db.query(Fixture).count()
        print(f"Existing fixtures before seeding: {existing}")

        team_ids = [row.id for row in db.query(Team.id).order_by(Team.id).all()]
        if not team_ids:
            raise SystemExit(
                "No teams in the database. Run migrate_hw05.py first - a fixture "
                "now requires a home team."
            )
        print(f"Home teams available: {len(team_ids)} (ids {team_ids[0]}..{team_ids[-1]})")

        # Continue the FX-9871-##### sequence after whatever is already there,
        # so codes stay unique without depending on auto-increment ids.
        highest = db.query(func.max(Fixture.fixture_code)).scalar()
        next_seq = int(highest.rsplit("-", 1)[1]) + 1 if highest else 1
        print(f"Next fixture_code sequence number: {next_seq}")

        print(f"Seeding {NUM_FIXTURES} fixtures...")
        batch = []
        for i in range(NUM_FIXTURES):
            team_a, team_b = random.sample(TEAM_NAMES, 2)
            city_a, city_b = random.sample(CITIES, 2)
            sport = random.choice(SPORTS)
            fixture = Fixture(
                fixture_name=f"{team_a} vs {team_b} ({sport} #{i+1})",
                teams_players=f"{city_a} {team_a} vs {city_b} {team_b}",
                fixture_code="FX-9871-%05d" % (next_seq + i),
                home_team_id=team_ids[i % len(team_ids)],
            )
            batch.append(fixture)
            if len(batch) >= 500:
                db.add_all(batch)
                db.commit()
                batch = []
        if batch:
            db.add_all(batch)
            db.commit()

        # Re-fetch actual ids assigned by MySQL (auto-increment)
        all_ids = [row.id for row in db.query(Fixture.id).all()]
        print(f"Total fixtures now in DB: {len(all_ids)}")

        print(f"Seeding {NUM_UPDATES} related fixture_updates rows...")
        update_batch = []
        for i in range(NUM_UPDATES):
            fid = random.choice(all_ids)
            update_batch.append(FixtureUpdate(
                fixture_id=fid,
                note=f"Update note #{i+1}: schedule confirmed.",
            ))
        db.add_all(update_batch)
        db.commit()

        total_fixtures = db.query(Fixture).count()
        total_updates = db.query(FixtureUpdate).count()
        print(f"\nDone. fixtures={total_fixtures}, fixture_updates={total_updates}")
    finally:
        db.close()


if __name__ == "__main__":
    main()