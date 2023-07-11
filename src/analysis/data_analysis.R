# Import required libraries
library(readr)
library(ggplot2)
library(scales)
library(forecast)
library(tseries)
library(MVN)
library(tsoutliers)
library(lmtest)
library(vars)

# Import dataset
CN_GeoServer <- read_csv("CN-GeoServer.csv")
View(CN_GeoServer)

# Remove failing builds
CN_GeoServer <- CN_GeoServer[!is.na(CN_GeoServer$COMPLEXITY), ]
View(CN_GeoServer)



#### PLOT START #####
# Convert the AUTHOR_DATE column to a Date object
CN_GeoServer$AUTHOR_DATE <- as.Date(CN_GeoServer$AUTHOR_DATE)

# Create a time series plot with two y-axes
p <- ggplot(CN_GeoServer, aes(x = AUTHOR_DATE)) +
  geom_line(aes(y = MICROSERVICES, color = "Number of microservices")) +
  geom_line(aes(y = SQALE_INDEX / max(CN_GeoServer$SQALE_INDEX, na.rm = TRUE) * max(CN_GeoServer$MICROSERVICES, na.rm = TRUE), color = "Technical debt (SQUALE index)")) +
  scale_color_manual(name = "", values = c("Number of microservices" = "orange", "Technical debt (SQUALE index)" = "blue")) +
  scale_x_date(labels = date_format("%m-%Y"), breaks = seq(min(CN_GeoServer$AUTHOR_DATE), max(CN_GeoServer$AUTHOR_DATE), by = "3 months")) +
  scale_y_continuous(name = "Number of microservices", limits = c(0, max(CN_GeoServer$MICROSERVICES, na.rm = TRUE)),
                     sec.axis = sec_axis(~ . * max(CN_GeoServer$SQALE_INDEX, na.rm = TRUE) / max(CN_GeoServer$MICROSERVICES, na.rm = TRUE), name = "Technical debt (SQUALE index)")) +
  labs(x = "Commit date") +
  theme_bw() +
  theme(text = element_text(family = "serif", size = 18),
        legend.position = "top",
        legend.box.background = element_blank(),
        legend.key.size = unit(0.5, "cm"),
        axis.text.x = element_text(angle = 30, hjust = 1))

# Save the plot to a file
ggsave("trend.pdf", plot = p, width = 10, height = 5)
#### PLOT END #####



#### POTENTIAL HOTSPOT IDENTIFICATION START #####

# Load the forecast package for the tsclean function
library(forecast)

# Convert the time series to a ts object
ts_data <- ts(CN_GeoServer$SQALE_INDEX)

# Detect outliers from the time series using the tsclean function
clean_ts_data <- tsclean(ts_data)

# Calculate the absolute difference between the original and cleaned time series
diff_ts_data <- abs(ts_data - clean_ts_data)

# Find the indices of the 10 largest absolute differences
outlier_indices <- order(diff_ts_data, decreasing = TRUE)[1:10]

# Store the rows with outliers in a new data frame
anomalous_rows <- CN_GeoServer[outlier_indices,]

# Write the anomalous rows to a CSV file
write.csv(anomalous_rows, file = "ts_outliers.csv", row.names = FALSE)


#### POTENTIAL HOTSPOT IDENTIFICATION ENDS #####



#### STL ANALYSIS START ####

# Create a time series object from the SQALE_INDEX column
SQALE_INDEX_ts <- ts(CN_GeoServer$SQALE_INDEX, frequency = 12)

# Decompose the time series using the STL algorithm
SQALE_INDEX_stl <- stl(SQALE_INDEX_ts, s.window = "periodic")

# Extract the seasonal, trend, and remainder components
SQALE_INDEX_seasonal <- SQALE_INDEX_stl$time.series[, "seasonal"]
SQALE_INDEX_trend <- SQALE_INDEX_stl$time.series[, "trend"]
SQALE_INDEX_remainder <- SQALE_INDEX_stl$time.series[, "remainder"]

# Create a data frame with the decomposed time series
SQALE_INDEX_decomposed <- data.frame(
  AUTHOR_DATE = rep(CN_GeoServer$AUTHOR_DATE, 3),
  Component = factor(rep(c("Trend", "Seasonal", "Irregular"), each = length(SQALE_INDEX_ts)), levels = c("Trend", "Seasonal", "Irregular")),
  Value = c(SQALE_INDEX_trend, SQALE_INDEX_seasonal, SQALE_INDEX_remainder)
)

# Create a plot showing the trend, seasonal, and irregular components one next to the other
p <- ggplot(SQALE_INDEX_decomposed, aes(x = AUTHOR_DATE, y = Value)) +
  geom_line(color = "blue") +
  facet_wrap(~ Component, ncol = 3) +
  scale_x_date(labels = date_format("%m-%Y"), breaks = seq(min(CN_GeoServer$AUTHOR_DATE), max(CN_GeoServer$AUTHOR_DATE), by = "3 months")) +
  labs(x = "Commit date", y = "Technical debt (SQUALE index)") +
  theme_bw() +
  theme(axis.text.x = element_text(angle = 30, hjust = 1),
        text=element_text(family="serif"))


ggsave("STL.pdf", plot = p, width = 10, height = 5)


# Extract the irregular component
SQALE_INDEX_irregular <- SQALE_INDEX_stl$time.series[, "remainder"]

# Add the irregular component to the data frame
CN_GeoServer$SQALE_INDEX_irregular <- SQALE_INDEX_irregular

# Select the 10 rows with the largest absolute irregular component
top_rows <- CN_GeoServer[order(abs(SQALE_INDEX_irregular), decreasing = TRUE), ][1:10, ]

# Write the selected rows to a CSV file
write.csv(top_rows[, c("COMMIT", "SQALE_INDEX_irregular")], "STL_identified_irregularities.csv", row.names = FALSE)
#### STL ANALYSIS END ####

#### START CORR ANALYSIS ####

# Calculate the z-scores of the SQALE_INDEX column
z_SQALE_INDEX <- scale(CN_GeoServer$SQALE_INDEX)

# Calculate the z-scores of the MICROSERVICES column
z_MICROSERVICES <- scale(CN_GeoServer$MICROSERVICES)

# make stationary
# Difference the SQALE_INDEX column
diff_SQALE_INDEX <- diff(z_SQALE_INDEX)

# Difference the MICROSERVICES column
diff_MICROSERVICES <- diff(z_MICROSERVICES)

# Set the font family for all text in the plot to "serif"
par(family="serif")

# Create a time series plot of the differenced data
plot(diff_SQALE_INDEX, type = "l", col = "blue",
     xlab = "Commit number", ylab = "Z-Score")
lines(diff_MICROSERVICES, col = "orange")
legend("top", legend = c("Technical Debt (SQUALE index)", "Number of microservices"),
       col = c("blue", "orange"), lty = 1, inset=c(0,-0.15), xpd=TRUE, bty="n", horiz=TRUE)


# Combine the differenced time series into a matrix
diff_data <- cbind(diff_SQALE_INDEX, diff_MICROSERVICES)

# Estimate an appropriate lag order for a VAR model using the VARselect function
var_select <- VARselect(diff_data, lag.max = 10, type = "const")

# Extract the estimated lag order from the VARselect output
lag_order <- var_select$selection["AIC(n)"]

# Print the estimated lag order
lag_order

# Perform a Granger causality test on the differenced data
granger_test <- grangertest(diff_SQALE_INDEX ~ diff_MICROSERVICES, order = 10)

# Print the results of the Granger causality test
granger_test

### RUN CORR ANALYSIS ON DERIVATES ###

# Calculate the derivatives of the SQALE_INDEX and MICROSERVICES columns
deriv_SQALE_INDEX <- diff(z_SQALE_INDEX, differences = 2)
deriv_MICROSERVICES <- diff(z_MICROSERVICES, differences = 2)

# Combine the derivatives into a matrix
deriv_data <- cbind(deriv_SQALE_INDEX, deriv_MICROSERVICES)

# Estimate an appropriate lag order for a VAR model using the VARselect function
var_select <- VARselect(deriv_data, lag.max = 10, type = "const")

# Extract the estimated lag order from the VARselect output
lag_order <- var_select$selection["AIC(n)"]

# Print the estimated lag order
lag_order

# Perform the ADF test on the derivatives
adf_deriv_SQALE_INDEX <- adf.test(deriv_SQALE_INDEX)
adf_deriv_MICROSERVICES <- adf.test(deriv_MICROSERVICES)

# Print the results of the ADF tests
adf_deriv_SQALE_INDEX
adf_deriv_MICROSERVICES

# Perform a Granger causality test on the derivatives
granger_test_deriv <- grangertest(deriv_SQALE_INDEX ~ deriv_MICROSERVICES, order = 10)

# Print the results of the Granger causality test
granger_test_deriv
