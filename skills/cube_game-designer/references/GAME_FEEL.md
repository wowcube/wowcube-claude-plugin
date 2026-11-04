# Game feel and cube composition: lessons from shipped builds

What players and testers reliably complained about, turned into design rules. Most of
them cost a full fix round when found after implementation.

How to use it: the **universal principles** apply to every game. Then pick the genre
sections that match the GDD's genre (one or two; a puzzle with a timer reads both
"Puzzle" and "Arcade / reflex"), apply them, and record in the GDD's Design Assumptions
which sections were used. A rule broken on purpose is listed there too, with the reason.

## Universal principles (every game)

### Readable feedback for every action
- **Every input has a visible answer** within one or two ticks: a twist, a tap, a tilt
  changes something on screen (a highlight, a move, a sound). An input that does
  nothing visible reads as a broken cube.
- **Moves glide, they do not teleport.** An object that jumps cell to cell instantly
  reads as broken; animate the move (its time is a tunable).
- **Success and failure look different** (colour, motion, sound): the player must know
  what happened without reading text.

### Threats and fair reaction time (when the game has threats)
- **Telegraph every threat**: a wind-up (about a second), a pose or colour change and a
  marker where it will land, so the player can react.
- **Make the danger zone visible** (a range, a path, a timer bar), and keep it slower
  than the player can respond: the cube is controlled by twisting and tilting, which is
  slower than a gamepad.
- Games without threats (puzzles, toys) still need fair time pressure: any timer or
  countdown is visible and generous on the first level.

### One tunables table
- **Every pace number in one table** in the GDD (move time, spawn or round interval,
  cooldowns, timers, scoring steps), marked whether it is expected to move. Expect two
  or three balance passes after the first playable build ("slower", then "a bit
  livelier").

### Composition across 24 screens
- Decide per element whether it lives on **one screen, one face, or every face** (a HUD
  usually repeats on each side face; the playfield usually lives on one face). Write it
  down: it is the first thing implementations get wrong.
- **Scenery spanning several screens is one picture** (a panorama) split per screen,
  continuous and upright around the four side faces. The same backdrop tile on every
  screen looks cheap.
- **Unique objects appear once on the cube.** A moon or a sun on every screen is a bug.
  Name the face and screen of each unique object and what happens when the cube turns.
- Games that follow the up face: say what the other faces show at the same time.

### Sound bed and event table
- The engine mixes several sounds per module: a music bed plus effects is the default (a
  game ships without music only when the GDD says so). Music is a short loop (10-20 s)
  the game restarts; a playing sound cannot be stopped.
- An **event table**: event -> sound -> mood -> where it plays. One sound per moment:
  when two events coincide, one combined sound, not two on the same tick.
- With `sound.source: cc0`, real recordings layered and mastered (CC0 sources, the user
  approves the list) beat quick synthesis by far, which only fills gaps. With `sound.source:
  synth` the user chose synthesized sound: it is the final sound, so give it the same care
  (a pitch and a character per event, a real music loop), never "placeholder" quality.

### Test hooks and delivery
- An **autoplay bot** switch: the game plays itself (screenshots, balance runs, the
  gameplay video). It exercises every mechanic, restarts rounds on its own and loses
  some rounds on purpose, so the death and retry path is seen too.
- A **scene** switch: each round starts one move from its win, or one step from its loss,
  so a short check reaches the ending of a long level or a maze.
- A **mute** switch for test builds.
- A **playfield pin**: forces the playfield to one face (screenshots without tilting).
  Games without a playfield face keep it unused.
- A **launcher icon** in the game's style; a short gameplay video is offered at delivery.

## Genre sections

### Action / shooter
- **A shot has weight**: a flash at the source, a burst of particles (procedural circles
  are enough), a recoil pose and a layered sound (blast + low thump + impact). One
  missing and the shot "does not feel".
- **The target reacts on the first hit** (a wounded look, a blink), then a clear defeat
  (a burst, a decal).
- **No "stand still and win"**: if the player can win without moving, the balance is
  wrong. A working starting set: regular opponents fall in 2 hits, a fire cooldown of
  about 1 s, a heavy opponent (5 hits, changes look after 2) that forces movement, a cap
  on opponents per screen (about 3 when the playfield is one face).
- A charge or dash from a distance is fun when it is frequent enough to matter: tune its
  frequency; show its path during the wind-up.

### Puzzle
- **The rule is learnable from the first screen**: level 1 teaches one idea with no way
  to fail; each later level adds one twist on it.
- **Undo or a cheap restart** (a double tap, a half twist): a wrong twist must not cost
  minutes.
- **State is readable at a glance**: what is solved, what is not, how far to go (a
  counter, a lit border). A solved state gets a short celebration.
- **Twists are the puzzle**: say which pieces move with a twist and which stay; a
  puzzle that ignores how the cube actually moves feels arbitrary.
- Hints after a stall (time or failed attempts), never a timer on the first levels.

### Arcade / reflex
- **Difficulty ramps by one number at a time** (speed, then spawn rate, then patterns)
  and the ramp is in the tunables table.
- **A run is short** (30 s to 3 min) and restarts in one tap; the score and the best
  score are always visible.
- Collisions are generous: the hit area is a little smaller than the drawn object.
- Effects stay within the frame rate: 20 updates per second, so very fast objects
  skip; cap speeds so that an object moves less than its own size per tick.

### Rhythm / music
- **Sound starts on the tick of its event**; the beat grid is in ticks (20 per second),
  so tempos are chosen to land on whole ticks (e.g. 120 BPM = a beat every 10 ticks).
- **Visual cues lead the beat** by a fixed, tunable number of ticks; the timing window
  is generous (at least 2 ticks either side) because input travels through the cube.
- The music loop is the clock: one loop length, retriggered by the game; no mechanic
  relies on stopping a sound.
- Judge timing on the real cube: the simulator plays sound on one module only.

### Idle / toy / screensaver
- **Something gentle moves all the time**, but faces that do not change are not
  redrawn: keep idle animation on few screens to save battery.
- **No failure state**, or a soft one; any input gives a pleasant reaction.
- After 60 s without input a game pauses (battery save); a screensaver-type app says
  "Category: screensaver" in the GDD's Genre section, and the scaffold sets `APP_CATEGORIES`
  from it (`new_app -Category screensaver`).
- Long sessions: avoid bright full-white screens and fast flicker.

### Kids / educational
- **No reading needed to play**: icons, colours and sounds carry the rules; text is a
  bonus for parents.
- **Mistakes are safe**: no harsh fail sound, no lost progress; retry is immediate.
- Large targets: per-screen taps on whole screens, never small spots.
- Short sessions (2-5 min) with a clear end and praise; progress is saved.
- No ads, no links, no data collection in the game.

### Narrative / adventure
- **One clear goal on screen at a time** (an object, a direction, a marker).
- Text is short: one line per screen, readable sizes (see the font numbers in API.md);
  a story beat never needs more than one face.
- Progress is saved at every scene change (the cube never resumes a game after sleep).
- Map the world to the cube deliberately: which face is "here", where the player goes
  next, what a twist means in the story.

### Party / multiplayer (several people around one cube)
- **Each player owns a face or a side** and sees their own state on it; shared state
  (score, timer) repeats on every face.
- Turns are announced with sound and a clear colour per player.
- Taps on the wrong face must not count for another player; say how simultaneous taps
  resolve.
- Rounds are short and the winner is shown on every face.
