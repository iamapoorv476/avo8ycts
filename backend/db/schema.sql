
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS fuelhh_actuals;
CREATE TABLE fuelhh_actuals (
    startTime         TEXT    PRIMARY KEY,   
    settlementDate    TEXT    NOT NULL,       
    settlementPeriod  INTEGER NOT NULL,       
    generation        NUMERIC NOT NULL        
);

DROP TABLE IF EXISTS windfor_forecasts;
CREATE TABLE windfor_forecasts (
    startTime     TEXT    NOT NULL,  
    publishTime   TEXT    NOT NULL,  
    generation    NUMERIC NOT NULL,  
    PRIMARY KEY (startTime, publishTime)
);

CREATE INDEX idx_windfor_latest_vintage
    ON windfor_forecasts (startTime, publishTime DESC);

DROP TABLE IF EXISTS decision_time_forecast;
CREATE TABLE decision_time_forecast (
    startTime            TEXT    PRIMARY KEY, 
    generation            NUMERIC NOT NULL,     
    source_publishTime    TEXT    NOT NULL      
);

DROP TABLE IF EXISTS matched_series;
CREATE TABLE matched_series (
    startTime         TEXT    PRIMARY KEY,  
    settlementPeriod  INTEGER NOT NULL,
    segment           TEXT    NOT NULL CHECK (segment IN ('PEAK', 'OFFPEAK')),
    forecast_mw       NUMERIC,              
    actual_mw         NUMERIC,              
    error_mw          NUMERIC GENERATED ALWAYS AS (forecast_mw - actual_mw) STORED,
                      
    included          INTEGER NOT NULL CHECK (included IN (0, 1)),  -- BOOLEAN
    exclusion_reason  TEXT    CHECK (
                          exclusion_reason IS NULL OR
                          exclusion_reason IN ('NO_FORECAST_BEFORE_CUTOFF', 'MISSING_OR_INVALID_ACTUAL')
                      ),
    floor_mw          NUMERIC,              
    advisory_text     TEXT                  
);

DROP TABLE IF EXISTS metrics_summary;
CREATE TABLE metrics_summary (
    scope_type       TEXT    NOT NULL CHECK (scope_type IN ('MONTH', 'RANGE')),
    scope_period     TEXT    NOT NULL,  
    segment          TEXT    NOT NULL CHECK (segment IN ('ALL', 'PEAK', 'OFFPEAK')),
    mbe              NUMERIC NOT NULL,
    mae              NUMERIC NOT NULL,
    rmse             NUMERIC NOT NULL,
    sigma_residual   NUMERIC NOT NULL,
    n                INTEGER NOT NULL,
    excluded_count   INTEGER NOT NULL,
    PRIMARY KEY (scope_type, scope_period, segment)
);