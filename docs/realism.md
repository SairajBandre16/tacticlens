# Simulator realism report

League sample: 300 full-mode matches between the 8 fictional clubs (seeded, reproducible).
Regenerate with `python -m tacticlens.sim realism`.

Engine: possession-chain simulator on a 12x8 zone grid. Each action (pass, dribble, shot, clearance) is
sampled from zone- and style-dependent probabilities (press_intensity, tempo, directness, width, quality);
pressing, fouls, cards, corners, free kicks, substitutions and fatigue are modelled. Shot outcomes come
from a hidden ground-truth scoring function that the xG model (M2) has to learn. Fast mode skips
coordinates and Event objects but replays the identical random stream, so a seed gives the same match.

| Metric | Target | Mean | p10 - p90 | Pass |
|---|---|---|---|---|
| Goals per match | 2.00 - 3.50 | 2.63 | 1.00 - 4.00 | yes |
| Shots per team | 9.0 - 16.0 | 13.7 | 10.5 - 17.0 | yes |
| Shots on target per team | 3.0 - 6.0 | 4.9 | 3.0 - 7.0 | yes |
| Passes per team | 350 - 600 | 427 | 396 - 457 | yes |
| Pass accuracy (%) | 75.0 - 88.0 | 83.8 | 82.1 - 85.6 | yes |
| Fouls per match | 18.0 - 26.0 | 20.9 | 14.0 - 28.0 | yes |
| Cards per match | 2.0 - 5.0 | 3.3 | 1.0 - 6.0 | yes |
| Corners per team | 3.5 - 6.5 | 5.0 | 3.0 - 7.0 | yes |
| Dominant-side possession (%) | 50.0 - 65.0 | 55.0 | 50.7 - 60.5 | yes |

**Overall: PASS** (league mean of every metric inside its target band).

## Golden matches

| Match | Story | Score | Shots H-A | Passes H-A | Cards |
|---|---|---|---|---|---|
| GM01 | Late comeback | Northbridge United 3-2 Kestrel Town | 22-10 | 468-383 | 2 |
| GM02 | Ten men | Harbor Athletic 1-0 Redmere FC | 18-13 | 519-374 | 6 |
| GM03 | Derby draw | Greyhaven Rovers 2-2 Thornvale City | 17-9 | 333-398 | 8 |
| GM04 | Press collapse | Kestrel Town 1-2 Harbor Athletic | 8-15 | 446-446 | 2 |
| GM05 | The rout | Northbridge United 4-0 Elmstead Wanderers | 21-2 | 530-348 | 1 |
| GM06 | Set-piece special | Redmere FC 1-0 Thornvale City | 16-11 | 426-491 | 2 |
