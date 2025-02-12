from flask import Flask, render_template
import threading
import time
from threading import Lock
from python_code.espn_tools.fantasy_data import FantasyData

app = Flask(__name__, 
    template_folder='../webpage_templates',
    static_folder='../webpage_files'
)

# Global variables to store our data
fantasy_data = []
data_lock = Lock()  # Thread safety for data updates

# Initialize our ESPN data fetcher
espn = FantasyData()

def update_data():
    """
    Background thread function that periodically updates fantasy data
    """
    global fantasy_data
    while True:
        # Fetch new data
        new_data = espn.get_all_fantasy_data()
        
        # Safely update our global data
        with data_lock:
            fantasy_data = new_data
            
        # Wait before next update (90 seconds by default)
        time.sleep(90)

# Prevent Flask from caching responses
@app.after_request
def add_header(response):
    response.cache_control.no_cache = True
    response.cache_control.must_revalidate = True
    response.cache_control.no_store = True
    return response

@app.route('/')
def index():
    """
    Main route that displays our fantasy page
    """
    with data_lock:
        current_data = fantasy_data
    return render_template('fantasy_page.html', fantasy_data=current_data)

if __name__ == "__main__":
    # Start the background data update thread
    update_thread = threading.Thread(target=update_data, daemon=True)
    update_thread.start()
    
    # Start the Flask application
    app.run(host="0.0.0.0", port=5000, debug=False)
