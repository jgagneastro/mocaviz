from dash import Dash, html, dcc
import dash

#conda install python-dotenv or pip install python-dotenv
from dotenv import load_dotenv
load_dotenv()  # take environment variables from .env.

app = Dash(__name__, use_pages=True)

app.layout = html.Div([
	html.H1('Multi-page app with Dash Pages'),

    html.Div(
        [
            html.Div(
                dcc.Link(
                    f"{page['name']} - {page['path']}", href=page["relative_path"]
                )
            )
            for page in dash.page_registry.values()
        ]
    ),

	dash.page_container
])

if __name__ == '__main__':
	app.run_server(debug=True)

# The following line is required by Phusion Passenger.
# It exposes the WSGI App using the application variable.
# by jmcouillard using this reference : https://community.plotly.com/t/deploying-dash-app-on-a-wsgi-service/57867
application = app.server
