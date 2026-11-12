# HW10 labelling sheet

Give each draft ONE helpfulness label, 1-5, by hand: 1 = very poor (wrong, evasive or off-topic), 2 = poor, 3 = adequate, 4 = good, 5 = excellent (accurate, relevant, useful).
Judge the DRAFT against the question and the facts that were supplied with it. Write the labels in human_labels.csv. Do not use an LLM, and do not change a label after you have seen judge scores.

## case_01

**Question sent to the pipeline:**

```
League database facts (authoritative; use them, do not invent other values):
- FX-9871-00012: "Strikers vs Bears (Volleyball #10)"; teams: Oakland Strikers vs Santa Clara Bears; home team: Oakland Panthers (home ground: Bushrod Park, Oakland); player spots available: 22.

Question: Which team is the home team for fixture FX-9871-00012?
```

**Writer draft:**

```
The home team for fixture FX-9871-00012 is the Oakland Panthers.
```

## case_02

**Question sent to the pipeline:**

```
League database facts (authoritative; use them, do not invent other values):
- FX-9871-00031: "Wolves vs Sharks (Soccer #29)"; teams: Milpitas Wolves vs Oakland Sharks; home team: Milpitas Eagles (home ground: Cardoza Park, Milpitas); player spots available: 22.

Question: How many player spots are still open on fixture FX-9871-00031, and which teams are playing?
```

**Writer draft:**

```
Fixture FX-9871-00031 has 22 player spots still open. The teams playing are the Milpitas Wolves and the Oakland Sharks.
```

## case_03

**Question sent to the pipeline:**

```
League database facts (authoritative; use them, do not invent other values):
- FX-9871-00044: "Sharks vs Falcons (Basketball #42)"; teams: Milpitas Sharks vs San Jose Falcons; home team: San Jose Sharks (home ground: Backesto Park, San Jose); player spots available: 22.

Question: Where will fixture FX-9871-00044 be played?
```

**Writer draft:**

```
Fixture FX-9871-00044 will be played at Backesto Park in San Jose. The home team, San Jose Sharks, is listed as the host for this basketball match.
```

## case_04

**Question sent to the pipeline:**

```
League database facts (authoritative; use them, do not invent other values):
- FX-9871-00057: "Tigers vs Titans (Cricket #55)"; teams: Fremont Tigers vs Oakland Titans; home team: Fremont Wolves (home ground: Northgate Park, Fremont); player spots available: 22.

Question: Name both teams in fixture FX-9871-00057 and say which one is at home.
```

**Writer draft:**

```
The fixture FX-9871-00057 features the Fremont Tigers and Oakland Titans. The home team is the Fremont Tigers, playing at Northgate Park in Fremont.
```

## case_05

**Question sent to the pipeline:**

```
League database facts (authoritative; use them, do not invent other values):
- FX-9871-00063: "Bears vs Wolves (Volleyball #61)"; teams: Santa Clara Bears vs Milpitas Wolves; home team: Fremont Warriors (home ground: Central Park Fields, Fremont); player spots available: 22.

Question: Is there room for 3 more players to register for fixture FX-9871-00063?
```

**Writer draft:**

```
The player spots available for FX-9871-00063 are 22. Since 22 is greater than 3, there is room for 3 more players to register for this fixture.
```

## case_06

**Question sent to the pipeline:**

```
League database facts (authoritative; use them, do not invent other values):
- FX-9871-00078: "Lions vs Tigers (Cricket #76)"; teams: Santa Clara Lions vs San Jose Tigers; home team: Oakland Titans (home ground: Mosswood Park, Oakland); player spots available: 22.

Question: What is the name of fixture FX-9871-00078?
```

**Writer draft:**

```
The name of fixture FX-9871-00078 is "Lions vs Tigers (Cricket #76)."
```

## case_07

**Question sent to the pipeline:**

```
League database facts (authoritative; use them, do not invent other values):
- FX-9871-09101: no such fixture exists in the league database.

Question: Which team is the home team for fixture FX-9871-09101?
```

**Writer draft:**

```
The league database indicates that fixture FX-9871-09101 does not exist. Since the fixture is not listed, the home team cannot be determined.
```

## case_08

**Question sent to the pipeline:**

```
League database facts (authoritative; use them, do not invent other values):
- FX-9871-09102: no such fixture exists in the league database.

Question: How many player spots are open on fixture FX-9871-09102?
```

**Writer draft:**

```
The league database confirms that fixture FX-9871-09102 does not exist. Since the fixture is not listed, there are no player spots open for it.
```

## case_09

**Question sent to the pipeline:**

```
Question: What should a league office check before scheduling a Soccer fixture on a shared field?
```

**Writer draft:**

```
Before scheduling a soccer fixture on a shared field, the league office should check the field's availability and booking status for the scheduled time. They should also verify that the field meets safety and maintenance standards to ensure a safe playing environment. Lastly, they must confirm there are no conflicting events or reservations for the field on that date to avoid scheduling conflicts.
```

## case_10

**Question sent to the pipeline:**

```
Question: How should a league office handle a team that cannot field enough players on match day?
```

**Writer draft:**

```
When a team cannot field enough players, the league office should first confirm the issue. Then, the team should be contacted to discuss the situation and explore options like rescheduling matches or temporarily adjusting team rosters. The office may also offer support, such as helping find additional players or adjusting game times. If necessary, the league may reassign matches to ensure fairness and continuity. Clear communication and flexibility are key to resolving the issue while maintaining the integrity of the league.
```

## case_11

**Question sent to the pipeline:**

```
Question: Explain how a round-robin schedule works for a six-team volleyball league.
```

**Writer draft:**

```
In a six-team volleyball round-robin, each team plays every other team twice—once at home and once away. This results in 10 matches per team. To create the schedule, pair teams in a way that each plays all others. For example, Team A plays Teams B, C, D, E, and F twice. Assign specific dates and times for each match, ensuring no team has more than one game per day. Rotate teams to balance the schedule and avoid conflicts. This format ensures fair competition and equal opportunities for all teams to face each other.
```

## case_12

**Question sent to the pipeline:**

```
Question: What information belongs in a fixture cancellation notice sent to both teams?
```

**Writer draft:**

```
The fixture cancellation notice should include the reason for the cancellation, such as weather or field unavailability. It must clearly state the affected match and its original date, time, and location. The notice should also provide an alternative date or outline next steps for rescheduling, such as contacting the league office or rebooking the match. This ensures both teams are informed and know how to proceed.
```

## case_13

**Question sent to the pipeline:**

```
Question: Why might a league cap the number of substitutions in a cricket match?
```

**Writer draft:**

```
Substitutions in cricket are used to replace injured or fatigued players, ensuring fair play and player safety. Limiting substitutions can increase the physical and mental demands on players, potentially reducing the likelihood of injuries. A substitution cap may also promote strategic depth, as teams must plan more carefully for potential setbacks. This rule can enhance the flow of the game, encourage stronger team cohesion, and prevent teams from relying too heavily on replacements, making the match more competitive and engaging for spectators.
```

## case_14

**Question sent to the pipeline:**

```
Question: What are three ways to reduce no-shows for early-morning basketball fixtures?
```

**Writer draft:**

```
Many people miss early-morning games due to lack of motivation, poor scheduling, or insufficient reminders. To reduce no-shows, offer flexible scheduling options like evening practices or weekend games. Send automated reminders via text or email the day before and morning of the game. Also, create a sense of community by encouraging team bonding and recognition of attendance. Track attendance data to assess the effectiveness of these strategies and adjust as needed.
```

## case_15

**Question sent to the pipeline:**

```
Question: How do you break a tie in league standings when two teams have the same points?
```

**Writer draft:**

```
If two teams have the same points, the league uses head-to-head results as the tie-breaker. We compare their matches against each other, giving priority to wins and goal differences. If still tied, we look at overall goal difference, then total goals scored. The team that meets these criteria is ranked higher. If all criteria are equal, the tie is resolved by a coin toss or draw.
```

## case_16

**Question sent to the pipeline:**

```
Question: What was the final score of last season's championship game?
```

**Writer draft:**

```
The championship game in question was last season's league finals. The official results are recorded in the league's sports database. According to the records, the final score was Team A 35, Team B 28. This outcome was confirmed by the league's official scoreboard and final standings.
```

## case_17

**Question sent to the pipeline:**

```
Question: What is the phone number of the league office?
```

**Writer draft:**

```
The phone number of the league office is 555-0199. This number can be found in the contact information section of the league's website or on official communication materials. It is the primary means of reaching the office for inquiries or registrations. If you need further assistance, you may also visit the office in person or send an email.
```

## case_18

**Question sent to the pipeline:**

```
League database facts (authoritative; use them, do not invent other values):
- FX-9871-00012: "Strikers vs Bears (Volleyball #10)"; teams: Oakland Strikers vs Santa Clara Bears; home team: Oakland Panthers (home ground: Bushrod Park, Oakland); player spots available: 22.

Question: Which referee is assigned to fixture FX-9871-00012?
```

**Writer draft:**

```
The provided league database facts do not mention a referee assigned to fixture FX-9871-00012. Therefore, the information is not available in the given data.
```

## case_19

**Question sent to the pipeline:**

```
Question: How much does it cost to register a team this season?
```

**Writer draft:**

```
The registration fee for this season is $300 per team. This rate applies to all standard divisions. If your team is in a special division or category, the fee may vary, so please check with the league office for confirmation. For the most accurate information, visit our website or contact us directly.
```

## case_20

**Question sent to the pipeline:**

```
Question: Summarise the weather forecast for this Saturday's fixtures.
```

**Writer draft:**

```
The Saturday fixtures are in Manchester, Birmingham, and Leeds. Manchester is expected to have sunny skies with a high of 18°C. Birmingham will experience light rain with a temperature around 16°C. Leeds is forecast to have cloudy conditions with a high of 17°C. Overall, the weather will be mild, with some rain in Birmingham. Teams should prepare for varying conditions, especially in the Midlands.
```
