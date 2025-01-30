import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import requests
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# 1) Fetch Top Cities Data (2020 & 2023)
# -----------------------------
CENSUS_API_KEY = "0cde1bf60b94ccd0d2e967e0e63aef9d488248b8"

def clean_city_name(city_name):
    # Split city and state
    try:
        parts = city_name.split(",")
        if len(parts) != 2:
            return city_name, ""
        
        city = parts[0].replace(" city", "").replace(" metropolitan government", "").replace("(balance)", "").strip()
        state = parts[1].strip()
        return city, state
    except:
        return city_name, ""

# Function to fetch census data with error handling
def fetch_census_data(year):
    logger.info(f"Fetching census data for year {year}")
    try:
        url = f"https://api.census.gov/data/{year}/acs/acs5?get=NAME,B01003_001E&for=place:*&key={CENSUS_API_KEY}"
        logger.info(f"Making request to: {url}")
        
        response = requests.get(url, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Census API returned status code {response.status_code}")
            logger.error(f"Response content: {response.text}")
            raise Exception(f"Census API returned status code {response.status_code}")
            
        json_data = response.json()
        if not json_data or len(json_data) < 2:
            logger.error(f"Census API returned invalid data format: {json_data}")
            raise Exception("Invalid data format received from Census API")
            
        logger.info(f"Successfully fetched data for {year}")
        df_year = pd.DataFrame(json_data[1:], columns=json_data[0])
        df_year.rename(columns={"B01003_001E": f"Population_{year}", "NAME": "City"}, inplace=True)
        df_year[f"Population_{year}"] = pd.to_numeric(df_year[f"Population_{year}"])
        
        # Extract city and state
        city_state = df_year['City'].apply(clean_city_name)
        df_year['City'] = [x[0] for x in city_state]
        df_year['State'] = [x[1] for x in city_state]
        return df_year
        
    except requests.exceptions.Timeout:
        logger.error(f"Request timed out for year {year}")
        raise Exception(f"Census API request timed out for year {year}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching data for year {year}: {str(e)}")
        raise Exception(f"Error fetching data for {year}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error for year {year}: {str(e)}")
        raise Exception(f"Unexpected error for {year}: {str(e)}")

# Fetch population data for 2020 and 2023
years = ["2020", "2023"]
dfs = []

for year in years:
    df_year = fetch_census_data(year)
    dfs.append(df_year)

# Combine data for both years
df_2020 = dfs[0].groupby(["City", "State"], as_index=False).max()  # Keep highest 2020 value per city
df_2023 = dfs[1].groupby(["City", "State"], as_index=False).max()  # Keep highest 2023 value per city

# Merge the datasets on City and State
df_merged = pd.merge(df_2020, df_2023, on=["City", "State"], suffixes=("_2020", "_2023"))

# Add state abbreviations dictionary
state_abbrev = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR', 'California': 'CA',
    'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE', 'Florida': 'FL', 'Georgia': 'GA',
    'Hawaii': 'HI', 'Idaho': 'ID', 'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA',
    'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME', 'Maryland': 'MD',
    'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN', 'Mississippi': 'MS', 'Missouri': 'MO',
    'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ',
    'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH',
    'Oklahoma': 'OK', 'Oregon': 'OR', 'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
    'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT',
    'Virginia': 'VA', 'Washington': 'WA', 'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY',
    'District of Columbia': 'DC'
}

# Convert state names to abbreviations
df_merged['State'] = df_merged['State'].map(state_abbrev)

# Calculate Period Change percentage
df_merged["Period Change (%)"] = ((df_merged["Population_2023"] - df_merged["Population_2020"]) / df_merged["Population_2020"]) * 100

# Store top 250 and top 100
df_all = df_merged.sort_values("Population_2023", ascending=False).head(250).copy()
df_top100 = df_all.head(100).copy()

# Format numbers for both dataframes
for df in [df_all, df_top100]:
    df["Rank"] = range(1, len(df) + 1)
    df["Population_2023"] = df["Population_2023"].apply(lambda x: f"{x:,.0f}")
    df["Population_2020"] = df["Population_2020"].apply(lambda x: f"{x:,.0f}")
    df["Period Change (%)"] = df["Period Change (%)"].apply(lambda x: f"{x:.2f}%")
    df.reset_index(drop=True, inplace=True)

# Reorder columns
df_all = df_all[["Rank", "City", "State", "Population_2020", "Population_2023", "Period Change (%)"]]
df_top100 = df_top100[["Rank", "City", "State", "Population_2020", "Population_2023", "Period Change (%)"]]

# -----------------------------
# 2) Create Bar Chart Data
# -----------------------------
# Load Market Data
df_vacancy = pd.read_csv('vacancy_rate.csv')
df_cap = pd.read_csv('cap_rate.csv')
df_rent = pd.read_csv('average_rent.csv')
df_trans = pd.read_csv('transaction_volume.csv')

# Ensure consistent asset type order
asset_type_order = ['Office', 'Industrial', 'Retail', 'Multifamily', 'Hospitality']

# Function to create vacancy rate figure
def create_vacancy_figure(selected_class='Average'):
    if selected_class == 'Average':
        column_name = 'VacancyRate - Average'
    else:
        column_name = f'VacancyRate - {selected_class}'
    df_vacancy['Vacancy Rate (%)'] = df_vacancy[column_name] * 100
    
    fig = px.bar(
        df_vacancy,
        x='PropertyType',
        y='Vacancy Rate (%)',
        color='Vacancy Rate (%)',
        color_continuous_scale=["#416E9C", "#7FA4CA", "#A1ACBD"],
        title="<u>Vacancy Rates by Asset Type</u>"
    )
    fig.update_layout(
        title_x=0.5,
        title_font_size=20,
        showlegend=False,
        xaxis={'categoryorder': 'array', 'categoryarray': asset_type_order},
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin={"t": 40, "b": 40, "l": 40, "r": 40}
    )
    fig.update_traces(
        hovertemplate="<span style='color:white'><b>%{x}</b><br>%{y:.1f}%</span>"
    )
    fig.update_xaxes(tickangle=45)
    return fig

# Function to create cap rate figure
def create_cap_rate_figure(selected_class='Average'):
    if selected_class == 'Average':
        column_name = 'CapRate - Average'
    else:
        column_name = f'CapRate - {selected_class}'
    df_cap['Cap Rate (%)'] = df_cap[column_name] * 100
    
    fig = px.bar(
        df_cap,
        x='PropertyType',
        y='Cap Rate (%)',
        color='Cap Rate (%)',
        color_continuous_scale=["#227868", "#44A895", "#97B0AA"],
        title="<u>Cap Rates by Asset Type</u>"
    )
    fig.update_layout(
        title_x=0.5,
        title_font_size=20,
        showlegend=False,
        xaxis={'categoryorder': 'array', 'categoryarray': asset_type_order},
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin={"t": 40, "b": 40, "l": 40, "r": 40}
    )
    fig.update_traces(
        hovertemplate="<span style='color:white'><b>%{x}</b><br>%{y:.1f}%</span>"
    )
    fig.update_xaxes(tickangle=45)
    return fig

# Function to create rent figure
def create_rent_figure(selected_class='Average'):
    if selected_class == 'Average':
        column_name = 'AverageRent_PSF - Average'
    else:
        column_name = f'AverageRent_PSF - {selected_class}'
    df_rent['Rent ($/sq ft)'] = df_rent[column_name]
    
    fig = px.bar(
        df_rent,
        x='PropertyType',
        y='Rent ($/sq ft)',
        color='Rent ($/sq ft)',
        color_continuous_scale=["#227868", "#44A895", "#97B0AA"],
        title="<u>Average Rent per Sq Ft</u>"
    )
    fig.update_layout(
        title_x=0.5,
        title_font_size=20,
        showlegend=False,
        xaxis={'categoryorder': 'array', 'categoryarray': asset_type_order},
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin={"t": 40, "b": 40, "l": 40, "r": 40}
    )
    fig.update_traces(
        hovertemplate="<span style='color:white'><b>%{x}</b><br>$%{y:.2f}</span>"
    )
    fig.update_xaxes(tickangle=45)
    return fig

# Create Transaction Volume Chart (no class filtering needed)
df_trans['Transaction Volume ($M)'] = df_trans['TransactionVolume - T-12 Months ($M)']

fig_trans = px.bar(
    df_trans,
    x='PropertyType',
    y='Transaction Volume ($M)',
    color='Transaction Volume ($M)',
    color_continuous_scale=["#416E9C", "#7FA4CA", "#A1ACBD"],
    title="<u>Transaction Volume (Millions)</u>"
)
fig_trans.update_layout(
    title_x=0.5,
    title_font_size=20,
    showlegend=False,
    xaxis={'categoryorder': 'array', 'categoryarray': asset_type_order},
    plot_bgcolor="white",
    paper_bgcolor="white",
    margin={"t": 40, "b": 40, "l": 40, "r": 40},
    yaxis=dict(tickformat=",")  # This will format numbers with commas
)
fig_trans.update_traces(
    hovertemplate="<span style='color:white'><b>%{x}</b><br>$%{y:,.0f}M</span>"
)
fig_trans.update_xaxes(tickangle=45)

# Initial figures
initial_vacancy_fig = create_vacancy_figure()
initial_cap_rate_fig = create_cap_rate_figure()
initial_rent_fig = create_rent_figure()

# -----------------------------
# 3) Build Dash Layout
# -----------------------------
app = dash.Dash(__name__, 
    external_stylesheets=[
        dbc.themes.FLATLY,
        "https://use.fontawesome.com/releases/v5.15.4/css/all.css"
    ]
)

# Add custom CSS
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Real Estate Market Insights</title>
        {%favicon%}
        {%css%}
        <style>
            .nav-link { color: #227868 !important; }
            .chart-container { 
                transition: all 0.3s ease;
                border-radius: 10px;
                overflow: hidden;
            }
            .chart-container:hover { 
                transform: scale(1.02);
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }
            .chart-card {
                border-radius: 10px;
                border: 1px solid #dee2e6;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                background-color: white;
                height: 100%;
            }
            .table-responsive {
                width: 100%;
                height: 100%;
                overflow: auto;
                -webkit-overflow-scrolling: touch;
            }
            .table-container {
		width: 100%
		height: 100%;
                display: flex;
                flex-direction: column;
            }
            .table-card {
                height: 100%;
                display: flex;
                flex-direction: column;
            }
            .table-card-body {
                flex: 1;
                overflow: auto;
                padding: 0 !important;
            }
            .responsive-table {
                width: 100%;
                height: 100%;
                table-layout: fixed;
            }
            .responsive-table th,
            .responsive-table td {
                padding: 8px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .responsive-table th {
                position: sticky;
                top: 0;
                z-index: 1;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

app.layout = dbc.Container(
    fluid=True,
    children=[
        # Header
        dbc.Row(
            dbc.Col(
                html.H1("Real Estate Market Insights", 
                       className="text-center mb-4", 
                       style={"color": "#227868"}),
                width=12
            )
        ),

        # Census Bureau Link
        dbc.Row(
            dbc.Col(
                dbc.Alert(
                    [
                        html.I(className="fas fa-chart-bar mr-2"),
                        "Explore the official Census Bureau interactive population visualization ",
                        html.A("here", 
                               href="https://www.census.gov/library/visualizations/interactive/2020-population-and-housing-state-data.html", 
                               target="_blank", 
                               style={"font-weight": "bold", "color": "white"}),
                        "."
                    ],
                    color="light",
                    style={"backgroundColor": "#416E9C", "color": "white"},
                    className="text-center",
                ),
                width=12,
                className="mb-4"
            )
        ),

        # Filter and Charts Section
        dbc.Row([
            # Left Column - Filters and Table
            dbc.Col([
                # City Filter
                html.Div([
                    html.Div([
                        html.H5(
                            "Filter by Top Cities",
                            style={
                                "backgroundColor": "#A1ACBD",
                                "color": "white",
                                "padding": "0.7rem",
                                "marginBottom": "0",
                                "borderRadius": "4px",
                                "display": "inline-block",
                                "verticalAlign": "middle",
                                "height": "38px",
                                "lineHeight": "1"
                            }
                        ),
                        html.Div([
                            dcc.Dropdown(
                                id="city-filter",
                                options=[
                                    {"label": "Top 250 Cities", "value": "All"},
                                    {"label": "Top 100 Cities", "value": 100},
                                    {"label": "Top 50 Cities", "value": 50},
                                    {"label": "Top 25 Cities", "value": 25},
                                    {"label": "Top 10 Cities", "value": 10}
                                ],
                                value="All",
                                clearable=False,
                                style={
                                    "border": "1px solid #A1ACBD",
                                    "borderRadius": "4px",
                                    "width": "150px",
                                    "backgroundColor": "#f8f9fa"
                                }
                            )
                        ], style={
                            "marginLeft": "10px",
                            "display": "inline-block",
                            "verticalAlign": "middle",
                            "position": "relative",
                            "zIndex": "1000"  # Higher z-index for dropdown container
                        })
                    ], style={
                        "display": "flex",
                        "alignItems": "center",
                        "gap": "10px",
                        "position": "relative",
                        "zIndex": "999"  # Slightly lower z-index for the flex container
                    })
                ], style={
                    "marginBottom": "20px",
                    "position": "relative",
                    "zIndex": "998"  # Base z-index for the outer container
                }),

                # Table Card
                dbc.Card(
                    [
                        dbc.CardHeader(
                            id="table-title", 
                            style={
                                "fontSize": "1.5rem", 
                                "backgroundColor": "#227868", 
                                "color": "white",
                                "padding": "0.7rem"
                            }
                        ),
                        dbc.CardBody([
                            dcc.Loading(
                                id="table-loading",
                                type="circle",
                                children=html.Div(
                                    id="filtered-table",
                                    className="table-responsive",
                                    style={
					"maxHeight": "980px",  # Fixed height (adjust as needed)
					"overflowY": "auto",  # Enables vertical scrolling
					"overflowX": "auto",  # Enables horizontal scrolling if needed
					"width": "100%",
					"border": "1px solid #dee2e6",
					"padding": "10px",
					"backgroundColor": "white"
                                    }
                                )
                            )
                        ], className="table-card-body")
                    ],
                    className="table-card h-100"
                )
            ], width={"size": 4, "offset": 0}),

            # Right Column - Charts
            dbc.Col([
                # Charts Header
                dbc.Card(
                    dbc.CardHeader(
                        html.H5("National Market Data",
                               className="mb-0",
                               style={
                                   "color": "white",
                                   "margin": "0"
                               }),
                        style={
                            "backgroundColor": "#227868",
                            "padding": "0.7rem",
                            "height": "auto"
                        }
                    ),
                    className="mb-3"
                ),
                
                # Class Filter with Label
                html.Div([
                    html.Div([
                        html.H5(
                            "Filter by Asset Quality",
                            style={
                                "backgroundColor": "#A1ACBD",
                                "color": "white",
                                "padding": "0.7rem",
                                "marginBottom": "0",
                                "borderRadius": "4px",
                                "display": "inline-block",
                                "verticalAlign": "middle",
                                "height": "38px",  # Match dropdown height
                                "lineHeight": "1"
                            }
                        ),
                        html.Div([
                            dcc.Dropdown(
                                id="class-filter",
                                options=[
                                    {"label": "Average", "value": "Average"},
                                    {"label": "Class A", "value": "Class A"},
                                    {"label": "Class B", "value": "Class B"},
                                    {"label": "Class C", "value": "Class C"}
                                ],
                                value="Average",
                                clearable=False,
                                style={
                                    "border": "1px solid #A1ACBD",
                                    "borderRadius": "4px",
                                    "width": "150px",
                                    "backgroundColor": "#f8f9fa"
                                }
                            )
                        ], style={
                            "marginLeft": "10px",
                            "display": "inline-block",
                            "verticalAlign": "middle",
                            "position": "relative",
                            "zIndex": "1000"  # Higher z-index for dropdown container
                        })
                    ], style={
                        "display": "flex",
                        "alignItems": "center",
                        "gap": "10px",
                        "position": "relative",
                        "zIndex": "999"  # Slightly lower z-index for the flex container
                    })
                ], style={
                    "marginBottom": "20px",
                    "position": "relative",
                    "zIndex": "998"  # Base z-index for the outer container
                }),

                # Charts Container
                dbc.Container([
                    # First Row of Charts
                    dbc.Row([
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="vacancy-rate",
                                        figure=initial_vacancy_fig,
                                        config={"displayModeBar": False},
                                        className="chart-container"
                                    )
                                ),
                                className="chart-card"
                            ),
                            md=6,
                            className="mb-3"
                        ),
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="cap-rate",
                                        figure=initial_cap_rate_fig,
                                        config={"displayModeBar": False},
                                        className="chart-container"
                                    )
                                ),
                                className="chart-card"
                            ),
                            md=6,
                            className="mb-3"
                        )
                    ]),
                    # Second Row of Charts
                    dbc.Row([
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="transaction-volume",
                                        figure=fig_trans,
                                        config={"displayModeBar": False},
                                        className="chart-container"
                                    )
                                ),
                                className="chart-card"
                            ),
                            md=6,
                            className="mb-3"
                        ),
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="property-type",
                                        figure=initial_rent_fig,
                                        config={"displayModeBar": False},
                                        className="chart-container"
                                    )
                                ),
                                className="chart-card"
                            ),
                            md=6,
                            className="mb-3"
                        )
                    ])
                ], fluid=True, className="px-0")
            ], md=8)
        ], className="mb-3"),

        # Footer
        dbc.Row(
            dbc.Col(
                html.Footer(
                    [
                        html.Hr(),
                        html.P([
                            "Data sources: U.S. Census Bureau ACS 5-Year Estimates (2022-2023)",
                            html.Br(),
                            f"Last updated: {datetime.now().strftime('%B %d, %Y')}",
                        ], className="text-muted text-center")
                    ]
                ),
                width=12
            )
        )
    ]
)

# Callbacks
@app.callback(
    [Output("filtered-table", "children"),
     Output("table-title", "children")],
    [Input("city-filter", "value")]
)
def update_table_and_title(filter_value):
    try:
        if filter_value == "All":
            filtered_df = df_all
            title = "Top 250 US Cities by Population"
        else:
            filtered_df = df_top100.head(int(filter_value))
            title = f"Top {filter_value} US Cities by Population"

        table = dbc.Table.from_dataframe(
            filtered_df,
            striped=True,
            bordered=True,
            hover=True,
            responsive=True,
            style={
                "fontSize": "0.9rem",
                "textAlign": "left",
                "whiteSpace": "nowrap"
            }
        )

        # Get table header and body
        header = table.children[0]
        body = table.children[1]

        # Update header styles
        for i, col in enumerate(header.children[0].children):
            width = {
                0: "7%",   # Rank
                1: "18%",  # City
                2: "10%",  # State
                3: "20%",  # Population 2020
                4: "20%",  # Population 2023
                5: "25%"   # Period Change
            }.get(i, "auto")
            
            if hasattr(col, 'style'):
                col.style.update({
			"width": width, 
			"minWidth": "50px",
			"whiteSpace": "normal",
			"overflow": "hidden",
			"textOverflow": "ellipsis"})
            else:
                col.style = {
			"width": width, 
			"minWidth": "50px",
			"whiteSpace": "normal",
			"overflow": "hidden",
			"textOverflow": "ellipsis"}


        return table, title
    except Exception as e:
        logger.error(f"Error in update_table_and_title: {str(e)}")
        return html.Div([
            html.P(f"Error updating table: {str(e)}", style={"color": "red"}),
            html.P("Please try refreshing the page.")
        ]), "Error Loading Data"

@app.callback(
    [Output("vacancy-rate", "figure"),
     Output("cap-rate", "figure"),
     Output("property-type", "figure")],
    Input("class-filter", "value")
)
def update_charts(selected_class):
    return (
        create_vacancy_figure(selected_class),
        create_cap_rate_figure(selected_class),
        create_rent_figure(selected_class)
    )

# -----------------------------
# 5) Run the App
# -----------------------------
if __name__ == "__main__":
    app.run_server(debug=True)
server = app.server