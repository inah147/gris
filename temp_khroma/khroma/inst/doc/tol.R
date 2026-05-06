## ----setup, include=FALSE-----------------------------------------------------
knitr::opts_chunk$set(
  collapse = TRUE,
  comment = "#>",
  out.width = "100%"
)

## ----packages-----------------------------------------------------------------
library(khroma)

## ----tol_quali_bright, fig.height = 2, fig.width = 7--------------------------
bright <- color("bright")
plot_scheme(bright(7), colours = TRUE, names = TRUE, size = 0.9)

## ----tol_quali_highcontrast, fig.height = 2, fig.width = 7--------------------
highcontrast <- color("high contrast")
plot_scheme(highcontrast(3), colours = TRUE, names = TRUE, size = 0.9)

## ----tol_quali_vibrant, fig.height=2, fig.width=7-----------------------------
vibrant <- color("vibrant")
plot_scheme(vibrant(7), colours = TRUE, names = TRUE, size = 0.9)

## ----tol_quali_muted, fig.height=2, fig.width=7-------------------------------
muted <- color("muted")
plot_scheme(muted(9), colours = TRUE, names = TRUE, size = 0.9)

## ----tol_quali_mediumcontrast, fig.height = 2, fig.width = 7------------------
mediumcontrast <- color("medium contrast")
plot_scheme(mediumcontrast(6), colours = TRUE, names = TRUE, size = 0.9)

## ----tol_quali_pale_dark, fig.height=2, fig.width=7---------------------------
pale <- color("pale")
plot_scheme(pale(6), colours = TRUE, names = TRUE, size = 0.9)

dark <- color("dark")
plot_scheme(dark(6), colours = TRUE, names = TRUE, size = 0.9)

## ----tol_quali_light, fig.height=2, fig.width=7-------------------------------
light <- color("light")
plot_scheme(light(9), colours = TRUE, names = TRUE, size = 0.9)

## ----tol_div_sunset, fig.height=2, fig.width=7--------------------------------
sunset <- color("sunset")
plot_scheme(sunset(11), colours = TRUE, size = 0.9)

## ----tol_div_nightfall, fig.height=2, fig.width=7-----------------------------
nightfall <- color("nightfall")
plot_scheme(nightfall(17), colours = TRUE, size = 0.9)

## ----tol_div_BuRd, fig.height=2, fig.width=7----------------------------------
BuRd <- color("BuRd")
plot_scheme(BuRd(9), colours = TRUE, size = 0.9)

## ----tol_div_PRGn, fig.height=2, fig.width=7----------------------------------
PRGn <- color("PRGn")
plot_scheme(PRGn(9), colours = TRUE, size = 0.9)

## ----tol_seq_YlOrBr, fig.height=2, fig.width=7--------------------------------
YlOrBr <- color("YlOrBr")
plot_scheme(YlOrBr(9), colours = TRUE, size = 0.9)

## ----tol_seq_iridescent, fig.height=2, fig.width=7----------------------------
iridescent <- color("iridescent")
plot_scheme(iridescent(23), colours = TRUE, size = 0.5)

## ----tol_seq_incandescent, fig.height=2, fig.width=7--------------------------
incandescent <- color("incandescent")
plot_scheme(incandescent(11), colours = TRUE, size = 0.5)

## ----tol_seq_rainbow, fig.height=2, fig.width=7-------------------------------
discrete_rainbow <- color("discrete rainbow")
plot_scheme(discrete_rainbow(14), colours = TRUE, size = 0.7)

## ----tol_seq_adjust, fig.height=2, fig.width=7--------------------------------
smooth_rainbow <- color("smooth rainbow")

## Start at purple instead of off-white
plot(smooth_rainbow(256, range = c(0.25, 1)))
## End at red instead of brown
plot(smooth_rainbow(256, range = c(0, 0.9)))

## ----tol_quali, echo=FALSE, fig.height = 2, fig.width = 7, fig.show='hold', fig.cap='Diagnostic maps for the bright, vibrant, muted and light (from top to bottom) qualitative color schemes.'----
set.seed(12345)
plot_map(bright(7))
plot_map(vibrant(7))
plot_map(muted(9))
plot_map(light(9))

## ----tol_div, echo=FALSE, fig.height = 2, fig.width = 7, fig.show='hold', fig.cap='Diagnostic maps for the sunset, BuRd and PRGn (from top to bottom) diverging color schemes.'----
set.seed(12345)
plot_map(sunset(11))
plot_map(nightfall(17))
plot_map(BuRd(9))
plot_map(PRGn(9))

## ----tol_div_map, echo=FALSE, fig.height = 7, fig.width = 7, out.width='50%', fig.show='hold', fig.cap='Diagnostic maps for the sunset, BuRd and PRGn diverging color schemes.'----
plot_tiles(color("sunset")(128), n = 256)
plot_tiles(color("nightfall")(128), n = 256)
plot_tiles(color("BuRd")(128), n = 256)
plot_tiles(color("PRGn")(128), n = 256)

## ----tol_seq, echo=FALSE, fig.height = 2, fig.width = 7, fig.show='hold', fig.cap='Diagnostic maps for the YlOrBr, iridescent, discrete rainbow and smooth rainbow (from top to bottom) sequential color schemes.'----
set.seed(12345)
plot_map(YlOrBr(9))
plot_map(iridescent(23))
plot_map(incandescent(11))
plot_map(discrete_rainbow(14))
plot_map(smooth_rainbow(23))

## ----tol_seq_map, echo=FALSE, fig.height = 7, fig.width = 7, out.width='50%', fig.show='hold', fig.cap='Diagnostic maps for the YlOrBr, iridescent and smooth rainbow sequential color schemes.'----
plot_tiles(color("YlOrBr")(128), n = 256)
plot_tiles(color("iridescent")(128), n = 256)
plot_tiles(color("incandescent")(128), n = 256)
plot_tiles(color("smooth rainbow")(128), n = 256)

