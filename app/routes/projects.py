import json
import os
from flask import (
    Blueprint, render_template, request, redirect, url_for, make_response
)
from typing import Dict, Any
import csv
from io import StringIO
from datetime import datetime

from app import app

projects_bp = Blueprint("projects", __name__, url_prefix="/projects")

# Global committee data cache
_committee_cache = {}
_committee_names = {}


def load_committee_names() -> Dict[str, str]:
    """Load committee code to name mapping from cache.json"""
    global _committee_names
    if _committee_names:
        return _committee_names
    
    cache_path = os.path.join(
        app.static_folder, 'data', 'committees', 'cache.json'
    )
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
            committee_contacts = cache_data.get('committee_contacts', {})
            _committee_names = {
                code: info.get('name', code) 
                for code, info in committee_contacts.items()
            }
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        app.logger.warning(
            f"Could not load committee names from {cache_path}"
        )
        _committee_names = {}
    
    return _committee_names


def scan_committee_files() -> Dict[str, Dict[str, Any]]:
    """Scan for basic_*.json files and build committee index"""
    global _committee_cache
    if _committee_cache:
        return _committee_cache
    
    committees_dir = os.path.join(app.static_folder, 'data', 'committees')
    committee_names = load_committee_names()
    
    for filename in os.listdir(committees_dir):
        if filename.startswith('basic_') and filename.endswith('.json'):
            # Extract committee code (e.g., 'J17' from 'basic_J17.json')
            code = filename[6:-5]  # Remove 'basic_' and '.json'
            
            file_path = os.path.join(committees_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    bills_data = json.load(f)
                
                # Get committee name from cache or fallback to code
                committee_name = committee_names.get(code, code)
                
                # Calculate basic metadata
                total_bills = len(bills_data)
                compliant_bills = sum(
                    1 for bill in bills_data 
                    if bill.get('state') == 'compliant'
                )
                non_compliant_bills = sum(
                    1 for bill in bills_data 
                    if bill.get('state') == 'non-compliant'
                )
                
                _committee_cache[code] = {
                    'code': code,
                    'name': committee_name,
                    'path': file_path,
                    'bills': bills_data,
                    'metadata': {
                        'total_bills': total_bills,
                        'compliant_bills': compliant_bills,
                        'non_compliant_bills': non_compliant_bills,
                        'compliance_rate': round(
                            (compliant_bills / total_bills * 100) 
                            if total_bills > 0 else 0, 1
                        ),
                        'last_updated': datetime.fromtimestamp(
                            os.path.getmtime(file_path)
                        ).strftime('%Y-%m-%d')
                    }
                }
            except (FileNotFoundError, json.JSONDecodeError) as e:
                app.logger.error(
                    f"Error loading committee file {filename}: {e}"
                )
    
    return _committee_cache


@projects_bp.route("/")
def index():
    """Projects landing page showing available projects"""
    # Load committee data for the committees project
    committees = scan_committee_files()
    
    # Calculate aggregate stats for committees project
    total_committees = len(committees)
    total_bills = sum(
        c['metadata']['total_bills'] for c in committees.values()
    )
    avg_compliance = round(
        sum(c['metadata']['compliance_rate'] for c in committees.values()) 
        / total_committees if total_committees > 0 else 0, 1
    )
    
    projects_data = [
        {
            'id': 'committees',
            'title': 'Committee Compliance Dashboard',
            'description': ('Track Massachusetts legislative committee '
                          'compliance with hearing notice requirements, '
                          'decision deadlines, and transparency rules.'),
            'url': url_for('projects.committees'),
            'status': 'active',
            'stats': {
                'committees': total_committees,
                'bills': total_bills,
                'avg_compliance': f"{avg_compliance}%"
            },
            'last_updated': (max(c['metadata']['last_updated'] 
                               for c in committees.values()) 
                           if committees else 'N/A')
        }
    ]
    
    return render_template("projects/index.html", projects=projects_data)


@projects_bp.route("/committees")
def committees():
    """Committee compliance dashboard"""
    committees_data = scan_committee_files()
    
    if not committees_data:
        return render_template("projects/committees/dashboard.html", 
                             error="No committee data available")
    
    # Get selected committee from query param or default to first
    selected_code = request.args.get('committee')
    if not selected_code or selected_code not in committees_data:
        selected_code = list(committees_data.keys())[0]
    
    selected_committee = committees_data[selected_code]
    
    return render_template("projects/committees/dashboard.html",
                         committees=committees_data,
                         selected_committee=selected_committee,
                         selected_code=selected_code)


@projects_bp.route("/committees/export/<code>")
def export_committee_csv(code):
    """Export committee data as CSV"""
    committees_data = scan_committee_files()
    
    if code not in committees_data:
        return "Committee not found", 404
    
    committee = committees_data[code]
    bills = committee['bills']
    
    # Apply filters from query parameters
    state_filter = request.args.get('state')
    
    filtered_bills = bills
    if state_filter and state_filter != 'all':
        filtered_bills = [b for b in filtered_bills 
                         if b.get('state') == state_filter]
    
    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow([
        'Bill ID', 'Title', 'Hearing Date', 'D60 Deadline', 'Effective Deadline', 
        'Notice Gap (Days)', 'Reported Out', 'Summary Present', 'Votes Present', 
        'Compliance State', 'Reason', 'Bill URL', 'Summary URL', 'Votes URL'
    ])
    
    # Data rows
    for bill in filtered_bills:
        writer.writerow([
            bill.get('bill_id', ''),
            bill.get('bill_title', ''),
            bill.get('hearing_date', ''),
            bill.get('deadline_60', ''),
            bill.get('effective_deadline', ''),
            bill.get('notice_gap_days', ''),
            'Yes' if bill.get('reported_out') else 'No',
            'Yes' if bill.get('summary_present') else 'No',
            'Yes' if bill.get('votes_present') else 'No',
            bill.get('state', ''),
            bill.get('reason', ''),
            bill.get('bill_url', ''),
            bill.get('summary_url', ''),
            bill.get('votes_url', '')
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    filename = f"{committee['name']}_compliance_data.csv"
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@projects_bp.route("/permalink")
def permalink():
    """Handle permalink redirects with preserved filter state"""
    committee = request.args.get('committee')
    state = request.args.get('state')
    
    # Build query string for redirect
    params = {}
    if committee:
        params['committee'] = committee
    if state:
        params['state'] = state
    
    return redirect(url_for('projects.committees', **params))
