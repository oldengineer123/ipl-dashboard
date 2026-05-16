-- IPL starter queries (DuckDB)
--
-- Run with the DuckDB CLI:
--   cd ~/Desktop/ipl_json/build
--   duckdb < ../queries.sql
--
-- Or interactively:
--   duckdb
--   .read /Users/raghav/Desktop/ipl_json/queries.sql
--
-- The opts below tell DuckDB the CSVs use standard double-quote escaping.
-- (Required because the Lucknow ground name contains a comma.)

.mode column
.headers on

CREATE OR REPLACE VIEW deliveries AS
  SELECT * FROM read_csv('deliveries.csv', header=True, quote='"', escape='"');
CREATE OR REPLACE VIEW matches AS
  SELECT * FROM read_csv('matches.csv', header=True, quote='"', escape='"');
CREATE OR REPLACE VIEW players AS
  SELECT * FROM read_csv('players.csv', header=True, quote='"', escape='"');
CREATE OR REPLACE VIEW grounds AS
  SELECT * FROM read_csv('grounds.csv', header=True, quote='"', escape='"');
CREATE OR REPLACE VIEW batter_innings AS
  SELECT * FROM read_csv('batter_innings.csv', header=True, quote='"', escape='"');
CREATE OR REPLACE VIEW bowler_innings AS
  SELECT * FROM read_csv('bowler_innings.csv', header=True, quote='"', escape='"');


-- 1. Team cut: win % batting first vs chasing
WITH inn AS (
  SELECT match_id,
         MIN(CASE WHEN innings_no=1 THEN batting_team END) AS bat1,
         MIN(CASE WHEN innings_no=2 THEN batting_team END) AS bat2
  FROM deliveries WHERE is_super_over=0 GROUP BY match_id
)
SELECT t AS team,
       COUNT(*) AS matches,
       ROUND(100.0*SUM(CASE WHEN m.winner=t AND inn.bat1=t THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN inn.bat1=t THEN 1 ELSE 0 END),0), 1) AS win_pct_bat_first,
       ROUND(100.0*SUM(CASE WHEN m.winner=t AND inn.bat2=t THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN inn.bat2=t THEN 1 ELSE 0 END),0), 1) AS win_pct_chasing
FROM matches m JOIN inn USING(match_id)
CROSS JOIN UNNEST([m.team1, m.team2]) AS u(t)
WHERE m.winner IS NOT NULL
GROUP BY t HAVING COUNT(*) >= 50
ORDER BY matches DESC;


-- 2. Batter cut: best strike rates in the death overs (16-20)
SELECT batter,
       SUM(runs_batter) AS runs,
       SUM(CASE WHEN extras_wides=0 THEN 1 ELSE 0 END) AS balls,
       ROUND(100.0*SUM(runs_batter)
             / NULLIF(SUM(CASE WHEN extras_wides=0 THEN 1 ELSE 0 END),0), 1) AS strike_rate
FROM deliveries
WHERE phase='death' AND is_super_over=0
GROUP BY batter HAVING balls >= 500
ORDER BY strike_rate DESC LIMIT 20;


-- 3. Bowler cut: best powerplay economy (overs 1-6)
SELECT bowler,
       SUM(CASE WHEN extras_wides=0 AND extras_noballs=0 THEN 1 ELSE 0 END) AS legal_balls,
       SUM(runs_total) AS runs_conceded,
       ROUND(6.0 * SUM(runs_total)
             / NULLIF(SUM(CASE WHEN extras_wides=0 AND extras_noballs=0 THEN 1 ELSE 0 END),0), 2) AS economy
FROM deliveries
WHERE phase='powerplay' AND is_super_over=0
GROUP BY bowler HAVING legal_balls >= 1000
ORDER BY economy ASC LIMIT 20;


-- 4. Ground cut: chasing success rate at each venue
WITH first_inn AS (
  SELECT match_id, venue, SUM(runs_total) AS first_total
  FROM deliveries WHERE innings_no=1 AND is_super_over=0
  GROUP BY match_id, venue
)
SELECT fi.venue,
       COUNT(*) AS matches,
       ROUND(AVG(first_total),1) AS avg_first_innings,
       ROUND(100.0*SUM(CASE WHEN m.win_by_wickets IS NOT NULL THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN m.winner IS NOT NULL THEN 1 ELSE 0 END),0), 1) AS chase_win_pct
FROM first_inn fi JOIN matches m USING(match_id)
GROUP BY fi.venue HAVING matches >= 30
ORDER BY matches DESC;


-- 5. Toss decision effect
SELECT toss_decision,
       COUNT(*) AS matches,
       SUM(CASE WHEN winner=toss_winner THEN 1 ELSE 0 END) AS toss_winner_won,
       ROUND(100.0*SUM(CASE WHEN winner=toss_winner THEN 1 ELSE 0 END)/COUNT(*),1) AS win_pct
FROM matches WHERE winner IS NOT NULL AND toss_decision IS NOT NULL
GROUP BY toss_decision ORDER BY matches DESC;


-- 6. Career top run-scorers
SELECT batter,
       SUM(runs_batter) AS runs,
       SUM(CASE WHEN extras_wides=0 THEN 1 ELSE 0 END) AS balls,
       ROUND(100.0*SUM(runs_batter)/NULLIF(SUM(CASE WHEN extras_wides=0 THEN 1 ELSE 0 END),0),1) AS strike_rate,
       COUNT(DISTINCT match_id) AS innings_batted
FROM deliveries WHERE is_super_over=0
GROUP BY batter ORDER BY runs DESC LIMIT 20;


-- 7. Career top wicket-takers (excluding run outs)
SELECT bowler,
       COUNT(*) AS wickets,
       COUNT(DISTINCT match_id) AS matches
FROM deliveries
WHERE is_wicket=1
  AND wicket_kind NOT IN ('run out','retired hurt','retired out','obstructing the field')
  AND is_super_over=0
GROUP BY bowler ORDER BY wickets DESC LIMIT 20;


-- 8. Most consistent finishers: SR + average in chases when wickets in hand low
-- (Skeleton — extend with situational filters as needed.)
SELECT batter,
       SUM(runs_batter) AS runs,
       SUM(CASE WHEN extras_wides=0 THEN 1 ELSE 0 END) AS balls,
       ROUND(100.0*SUM(runs_batter)/NULLIF(SUM(CASE WHEN extras_wides=0 THEN 1 ELSE 0 END),0),1) AS strike_rate
FROM deliveries
WHERE innings_no=2 AND phase='death' AND is_super_over=0
GROUP BY batter HAVING balls >= 200
ORDER BY strike_rate DESC LIMIT 15;


-- ============================================================================
-- The queries below use the derived per-innings tables (batter_innings,
-- bowler_innings). They are smaller (~4 MB combined vs 49 MB for deliveries)
-- and let you write career-level splits without the wides-vs-balls-faced
-- gymnastics. Use them whenever you don't need ball-by-ball detail.
-- ============================================================================


-- 9. Career stats vs a specific opposition (Mumbai Indians)
SELECT batter,
       COUNT(*) AS innings,
       SUM(runs) AS runs,
       SUM(balls) AS balls,
       ROUND(100.0*SUM(runs)/NULLIF(SUM(balls),0),1) AS strike_rate,
       SUM(is_out) AS dismissals,
       ROUND(1.0*SUM(runs)/NULLIF(SUM(is_out),0),1) AS average
FROM batter_innings
WHERE bowling_team='Mumbai Indians' AND is_super_over=0
GROUP BY batter HAVING SUM(runs) >= 300
ORDER BY runs DESC LIMIT 20;


-- 10. Best individual batting performances ever (single innings)
SELECT match_date, batter, batting_team, bowling_team AS opposition, venue,
       runs, balls, strike_rate
FROM batter_innings
WHERE is_super_over=0
ORDER BY runs DESC LIMIT 20;


-- 11. Best bowling figures in a single innings
SELECT match_date, bowler, bowling_team, batting_team AS opposition, venue,
       overs, runs_conceded, wickets, economy
FROM bowler_innings
WHERE is_super_over=0
ORDER BY wickets DESC, runs_conceded ASC LIMIT 20;


-- 12. Opener-specific career stats (batting positions 1 and 2)
SELECT batter,
       COUNT(*) AS innings_opened,
       SUM(runs) AS runs,
       ROUND(100.0*SUM(runs)/NULLIF(SUM(balls),0),1) AS strike_rate,
       ROUND(1.0*SUM(runs)/NULLIF(SUM(is_out),0),1) AS average
FROM batter_innings
WHERE batting_position IN (1,2) AND is_super_over=0
GROUP BY batter HAVING innings_opened >= 30
ORDER BY runs DESC LIMIT 20;


-- 13. Career bowling: average, strike rate, and economy at a glance
SELECT bowler,
       COUNT(*) AS innings,
       SUM(legal_balls) AS balls,
       SUM(runs_conceded) AS runs,
       SUM(wickets) AS wickets,
       ROUND(1.0*SUM(runs_conceded)/NULLIF(SUM(wickets),0),2) AS bowling_avg,
       ROUND(1.0*SUM(legal_balls)/NULLIF(SUM(wickets),0),2) AS bowling_sr,
       ROUND(6.0*SUM(runs_conceded)/NULLIF(SUM(legal_balls),0),2) AS economy
FROM bowler_innings
WHERE is_super_over=0
GROUP BY bowler HAVING SUM(wickets) >= 50
ORDER BY wickets DESC LIMIT 20;


-- 14. Performance at a specific ground (Wankhede): top run-scorers
SELECT batter,
       COUNT(*) AS innings,
       SUM(runs) AS runs,
       ROUND(100.0*SUM(runs)/NULLIF(SUM(balls),0),1) AS strike_rate,
       SUM(fours) AS fours,
       SUM(sixes) AS sixes
FROM batter_innings
WHERE venue='Wankhede Stadium' AND is_super_over=0
GROUP BY batter HAVING SUM(runs) >= 300
ORDER BY runs DESC LIMIT 15;


-- 15. Season-by-season trajectory for a single player (Kohli)
SELECT season,
       COUNT(*) AS innings,
       SUM(runs) AS runs,
       ROUND(100.0*SUM(runs)/NULLIF(SUM(balls),0),1) AS strike_rate,
       ROUND(1.0*SUM(runs)/NULLIF(SUM(is_out),0),1) AS average,
       SUM(fours) AS fours, SUM(sixes) AS sixes
FROM batter_innings
WHERE batter='V Kohli' AND is_super_over=0
GROUP BY season ORDER BY season;
