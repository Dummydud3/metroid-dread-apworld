-- Metroid Bread loading tip pools (TITLE||BODY).
--
-- EDIT THIS FILE to add tips. Keep each entry under ~200 characters
-- (OdrTip caption limit is 240 including {c6}/{c7}/{c0} codes).
--
-- ApTipPool (default / always-on):
--   Always in the active generic carousel once the Hub client is connected.
--
-- ApTipPoolSecondary (progress unlocks):
--   For each Location_Collected check on this save, the next tip from this
--   list is unlocked into the active generic pool (in order, one per check).
--   Example: 0 checks → only ApTipPool; 3 checks → ApTipPool + first 3 here.
--   PrepareGenericCarousel still shows up to 5 tips at a time, shuffled from
--   the unlocked set.
--
-- Priority tips (Death Link / local death / early CONNECT CLIENT) are handled
-- separately in ap_loading_tips.lua and temporarily replace this carousel.

ApTipPool = {
  "{c6}DNA COUNTER{c7}||Metroid DNA fills the HUD DNA counter toward your Required DNA goal. Network Stations can hint DNA locations when that option is on.{c0}",
  "{c6}WARP HOTKEYS{c7}||ZL+D-Pad Left = last checkpoint. ZR+D-Pad Right = last Save, Map, or Network Station. Useful when you get stuck somewhere.{c0}",
  "{c6}DEATH LINK{c7}||When Death Link is on, other players' deaths can kill you, and yours can kill them. I'd avoid large angry Mawkins if I were you.{c0}",
  "{c6}HUB LOGS{c7}||Enable Debug logs in the Hub only when troubleshooting. Normal play keeps tip and map probe spam out of the main log.{c0}",
  "{c6}MAP TRACKER{c7}||Your map is constantly updating to show you new areas you can reach, and checks you can collect.{c0}",
}

-- Unlocked one-per-collected-check into the active generic pool (ordered).
ApTipPoolSecondary = {
  "{c6}CHARGE BEAM{c7}||Charge Beam opens Charge doors and charges shots. If you don't have this item by now, I'm so sorry for you.{c0}",
  "{c6}MORPH BALL{c7}||Why can't Metroid crawl?{c0}",
  "{c6}MISSILES{c7}||Aren't you so happy you fought Z-57 for 20 minutes to get that missile tank?{c0}",
  "{c6}BOMBS{c7}||Realistically the most appropriately balanced bird in Angry Birds Epic.{c0}",
  "{c6}SLIDE{c7}||Could you imagine if we randomized Slide? You'd get BK'ed at the beginning of the game.{c0}",
  "{c6}VARIA SUIT{c7}||A real man never speaks ill of Samus' Varia Suit.{c0}",
  "{c6}SPIDER MAGNET{c7}||Of course I have the Peter Tingle, just not for Bread.{c0}",
  "{c6}SPEED BOOSTER{c7}||In layman's terms, speedy thing goes in, speedy thing comes out. - GLaDOS{c0}",
  "{c6}FLASH SHIFT{c7}||Flash Shift is that item that makes people happy when they get it. We can finally be faster now.{c0}",
  "{c6}POWER SUIT{c7}||What is wrong with you? Why are you blue?{c0}",
  "{c6}PHANTOM CLOAK{c7}||Are you seriously a Phantom Cloak user? Forget that, go die to an EMMI seventeen times like a real man.{c0}",
  "{c6}WIDE BEAM{c7}||SPAZER BEAM. It's called the SPAZER beam. Not wide beam, not three shot beam, its SPAZER BEAM.{c0}",
  "{c6}DIFFUSION BEAM{c7}||Diffusion beam? Diffusion? Fusion? Metroid Fusion? GUYS DOES THIS MEAN METROID FUSION REMAKE?{c0}",
  "{c6}SUPER MISSILES{c7}||Remember missiles? You know how ordinary and average they are? Hear me out, what if we made them... Super?{c0}",
  "{c6}POWER BOMBS{c7}||Power Bombs clear PB blocks and some Enky / knowledge tricks. Ammo tanks matter as much as the main item.{c0}",
  "{c6}SPIN BOOST{c7}||Spin Boost adds air control for tall rooms. Space Jump is the full flight upgrade on Progressive Spin.{c0}",
  "{c6}SCREW ATTACK{c7}||I have become death, destroyer of worlds.{c0}",
  "{c6}PULSE RADAR{c7}||Remember those voices you keep hearing in your walls? Use your Pulse Radar to find them.{c0}",
  "{c6}NETWORK HINTS{c7}||Network Stations can roll AP hints (including DNA) depending on your YAML. Stop by when you are stuck.{c0}",
  "{c6}SAVE OFTEN{c7}||Save Stations and checkpoints are your friends. Would be a shame if you died in 23 seconds.{c0}",
  "{c6}EMMI ZONES{c7}||Just because you think you're good at this game does not mean you won't get jumped by Yellow EMMI.{c0}",
  "{c6}BOSS CHECKS{c7}||Bosses and EMMI's can be checks if you enable it. Especially fun for the All Bosses game goal.{c0}",
  "{c6}TRANSPORTS{c7}||What kind of Chozo infrastructure doesn't include elevator music?{c0}",
  "{c6}DOOR RANDO{c7}||Door randomization changes the kinds of locks that are put on doors.{c0}",
  "{c6}OUT OF LOGIC{c7}||Only naighty people get this tooltip. You went out of logic. I can smell it. Go back where you belong, punk.{c0}",
  "{c6}ENERGY TANKS{c7}||If some bosses don't seem to be in logic, you might need more health. Stop being a sweat.{c0}",
  "{c6}STORM MISSILES{c7}||Please stop overlooking this ability, it does so much damage.{c0}",
  "{c6}ICE MISSILES{c7}||American law enforement is equipped with Ice Missiles by voice command, telling suspects to freeze.{c0}",
  "{c6}WAVE BEAM{c7}||Why can't Samus just Wave Beam snipe Raven Beak from all the way down here?{c0}",
  "{c6}GRAVITY SUIT{c7}||MAGIC PANCAKES???{c0}",
}
