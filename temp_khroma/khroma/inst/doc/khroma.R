## ----include = FALSE----------------------------------------------------------
knitr::opts_chunk$set(
  collapse = TRUE,
  comment = "#>"
)

## ----setup--------------------------------------------------------------------
library(khroma)

## ----usage-show, fig.height=2, fig.width=7, fig.align='center'----------------
## Paul Tol's bright color scheme
bright <- color("bright")

## Get seven colors
bright(7)

## ----discrete-colors, fig.height=7, fig.width=7, fig.align='center'-----------
## Associate each species with a color
bright <- c(versicolor = "#4477AA", virginica = "#EE6677", setosa = "#228833")

## Build a palette function
pal_color <- palette_color_discrete(bright)

## Plot
plot(
  x = iris$Petal.Length,
  y = iris$Sepal.Length,
  col = pal_color(iris$Species), # Map species to colors
  pch = 16,
  xlab = "Petal length",
  ylab = "Sepal length",
  panel.first = grid(),
  las = 1
)
legend("topleft", legend = names(bright), col = bright, pch = 16)

## ----discrete-highlight, fig.height=7, fig.width=7, fig.align='center'--------
## Associate only one species with a color
bright <- c(versicolor = "#4477AA")

## Build a palette function
pal_color <- palette_color_discrete(bright)

## Plot
plot(
  x = iris$Petal.Length,
  y = iris$Sepal.Length,
  col = pal_color(iris$Species),
  pch = 16,
  xlab = "Petal length",
  ylab = "Sepal length",
  panel.first = grid(),
  las = 1
)
legend("topleft", legend = names(bright), col = bright, pch = 16)

## ----discrete-symbols, fig.height=7, fig.width=7, fig.align='center'----------
## Associate each species with a color
bright <- c(versicolor = "#4477AA", virginica = "#EE6677", setosa = "#228833")
pal_color <- palette_color_discrete(colors = bright)

## Associate each species with a symbol
symbols <- c(versicolor = 15, virginica = 16, setosa = 17)
pal_shapes <- palette_shape(symbols)

## Plot
plot(
  x = iris$Petal.Length,
  y = iris$Sepal.Length,
  col = pal_color(iris$Species), # Map species to colors
  pch = pal_shapes(iris$Species), # Map species to symbols
  xlab = "Petal length",
  ylab = "Sepal length",
  panel.first = grid(),
  las = 1
)
legend("topleft", legend = names(bright), col = bright, pch = symbols)

## ----discrete-sequential, fig.height=7, fig.width=7, fig.align='center'-------
## Scatter plot
## Build a color palette function
YlOrBr <- color("YlOrBr")
pal_color <- palette_color_continuous(colors = YlOrBr)

## Build a symbol palette function
pal_size <- palette_size_sequential(range = c(1, 3))

## Plot
plot(
  x = iris$Petal.Length,
  y = iris$Sepal.Length,
  pch = 16,
  col = pal_color(iris$Petal.Length),
  cex = pal_size(iris$Petal.Length),
  xlab = "Petal length",
  ylab = "Sepal length",
  panel.first = grid(),
  las = 1
)

