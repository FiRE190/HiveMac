# Landmark Templates

Place cropped PNG screenshots of BSS landmarks here.
One file per landmark, named exactly as the landmark ID.

Examples:
  hive_exterior.png        — cropped shot of the hive front face
  red_cannon.png           — cropped shot of the red cannon barrel
  mushroom_platform.png    — cropped shot of the mushroom cap edge
  spawn_platform.png       — cropped shot of spawn platform boards
  sunflower_field.png      — representative sunflower patch
  dandelion_field.png      — representative dandelion patch

Capture tips:
  - Crop tightly to the distinctive feature (not sky/ground padding)
  - Capture at a distance you expect the navigator to see from
  - Use the calibration tool's template capture tab to save images here
  - Higher-contrast, distinctive crops produce better match results

Without a template, the landmark detector falls back to HSV color matching
only (weaker confidence — adequate for common fields, less reliable for
uncommon landmarks like spawn_platform).
