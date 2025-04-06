import sys, os
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template
import logging
import json
import time
import asyncio
from werkzeug.utils import secure_filename
import traceback
import atexit
import shutil
from datetime import datetime
from werkzeug.serving import run_simple
from backend.services.agent import RFPRequirementAgent

# Configure logging properly
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

# Update path handling
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(current_dir, 'backend')
sys.path.append(backend_dir)

# Import services first
from backend.services.comparison_service import DocumentComparison
from backend.services.report import ReportGenerator
from backend.core.configure import get_report_config

# Initialize event loop for async operations
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def init_services():
    """Initialize all required services"""
    try:
        logger.info("Initializing services...")
        
        # Create necessary directories
        chromadb_path = os.path.join("backend", "data", "chromadb")
        reports_dir = os.path.join("backend", "reports")
        for path in [chromadb_path, reports_dir]:
            if os.path.exists(path):
                shutil.rmtree(path)
            os.makedirs(path, exist_ok=True)
            
        config = get_report_config()
        doc_comparison = DocumentComparison()
        report_generator = ReportGenerator()
        rfp_agent = RFPRequirementAgent()  # Initialize new agent
        
        # Test connections
        test_result = doc_comparison.parser.test_embedding()
        if test_result["status"] != "success":
            raise Exception("Embedding test failed")
            
        logger.info("Services initialized successfully")
        return config, doc_comparison, report_generator, rfp_agent
    except Exception as e:
        logger.error(f"Service initialization failed: {str(e)}")
        raise

# Initialize services
config, doc_comparison, report_generator, rfp_agent = init_services()

# Initialize services with proper cleanup
def cleanup_resources():
    """Cleanup function to be called on exit"""
    try:
        if 'doc_comparison' in globals():
            doc_comparison._cleanup()
        if 'loop' in globals():
            loop.close()
    except Exception as e:
        print(f"Cleanup failed: {str(e)}")

# Register cleanup function
atexit.register(cleanup_resources)

# Configure app
app = Flask(__name__,
    template_folder=os.path.join(backend_dir, 'templates'),
    static_folder=os.path.join('frontend', 'static')
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
async def upload_documents():
    try:
        if 'rfp_document' not in request.files or 'company_document' not in request.files:
            return jsonify({"error": "Both files are required"}), 400

        rfp_file = request.files['rfp_document']
        company_file = request.files['company_document']

        # Read binary content
        rfp_content = rfp_file.read()
        company_content = company_file.read()

        # Compare documents
        result = await doc_comparison.compare_documents(
            rfp_content=rfp_content,
            company_content=company_content
        )

        return jsonify({
            "status": "success",
            "data": result
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
async def analyze_documents():
    try:
        if 'rfp_document' not in request.files or 'company_document' not in request.files:
            return jsonify({"error": "Missing required files"}), 400

        rfp_file = request.files['rfp_document']
        company_file = request.files['company_document']

        # Read file contents
        rfp_content = rfp_file.read()
        company_content = company_file.read()

        # Get custom format requirements from request
        custom_format_reqs = request.form.get('format_requirements', {})
        if custom_format_reqs:
            try:
                custom_format_reqs = json.loads(custom_format_reqs)
            except:
                custom_format_reqs = {}

        # Default format requirements
        default_format_reqs = {
            "document_specs": {
                "page_limit": 30,
                "font": "Times New Roman, 12pt",
                "spacing": "1.5 line spacing",
                "margins": "1 inch all sides"
            },
            "submission_requirements": [
                "Table of Contents required",
                "Executive Summary (max 2 pages)",
                "Technical Proposal (max 25 pages)",
                "Cost Proposal (separate document)"
            ],
            "compliance_checklist": [
                {
                    "requirement": "ISO 9001 Certification",
                    "reasoning": "Required for quality management standards"
                },
                {
                    "requirement": "Security Clearance",
                    "reasoning": "Mandatory for handling sensitive data"
                }
            ]
        }

        # Merge custom requirements with defaults
        format_requirements = {
            **default_format_reqs,
            **(custom_format_reqs or {})
        }

        # Get all required analyses first
        comparison_result = await doc_comparison.compare_documents(
            rfp_content=rfp_content,
            company_content=company_content
        )
        
        eligibility_result = await doc_comparison.get_result(
            rfp_content=rfp_content,
            company_content=company_content
        )

        # Create analysis result before using it
        analysis_result = {
            "matches": comparison_result.get("matches", []),
            "scores": eligibility_result.get("scores", {}),
            "eligible": eligibility_result.get("eligible", False)
        }

        # Combine results with better structure
        analysis_data = {
            "rfp_name": rfp_file.filename,
            "date": datetime.now().strftime('%Y-%m-%d %H:%M'),
            "matches": comparison_result.get("matches", []),
            "match_statistics": comparison_result.get("match_statistics", {}),
            "total_chunks_processed": comparison_result.get("total_chunks_processed", {}),
            "scores": eligibility_result.get("scores", {}),
            "eligible": eligibility_result.get("eligible", False),
            "format_requirements": format_requirements,
            "formatting_validation": rfp_agent.validate_formatting(
                rfp_content.decode('utf-8', errors='ignore'),
                format_requirements
            ),
            "conditions": {
                "technical_match": eligibility_result.get("scores", {}).get("technical_match", 0) > 70,
                "coverage_sufficient": eligibility_result.get("scores", {}).get("requirement_coverage", 0) > 75
            },
            "compliance_analysis": {
                "checklist": [
                    {
                        "item": req.get("requirement", ""),
                        "status": "Required",
                        "reasoning": req.get("reasoning", "No reasoning provided")
                    }
                    for req in format_requirements.get("compliance_checklist", [])
                ],
                "risks": report_generator._analyze_risks(analysis_result)
            }
        }

        # Generate report with AI insights
        report_result = await report_generator.generate_report(
            analysis_result=analysis_data,
            rfp_name=rfp_file.filename
        )

        return jsonify({
            "status": "success",
            "report_id": report_result["report_id"],
            "redirect_url": f"/view-report/{report_result['report_id']}",
            "eligible": eligibility_result["eligible"],
            "scores": eligibility_result["scores"],
            "ai_insights": analysis_data.get("ai_insights", {})
        })

    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}", exc_info=True)
        return jsonify({"error": "Analysis failed", "details": str(e)}), 500

@app.route('/api/results/<report_id>')
def get_report(report_id):
    try:
        result = doc_comparison.get_result_by_id(report_id)
        if not result:
            return jsonify({"error": "Report not found"}), 404
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/format-requirements/<report_id>')
async def get_format_requirements(report_id):
    try:
        json_path = os.path.join(config.reports_dir, report_id, f"{report_id}.json")
        if not os.path.exists(json_path):
            return jsonify({"error": "Report not found"}), 404
            
        with open(json_path, 'r') as f:
            report_data = json.load(f)
            
        return jsonify({
            "format_requirements": report_data.get("format_requirements", {}),
            "report_id": report_id
        })
    except Exception as e:
        logger.error(f"Failed to get format requirements: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/ai-analysis/<report_id>')
async def get_ai_analysis(report_id):
    try:
        json_path = os.path.join(config.reports_dir, report_id, f"{report_id}.json")
        if not os.path.exists(json_path):
            return jsonify({"error": "Report not found"}), 404
            
        with open(json_path, 'r') as f:
            report_data = json.load(f)
            
        return jsonify({
            "ai_insights": report_data.get("ai_insights", {
                "required_qualifications": "Analysis not available",
                "risk_assessment": "Risk analysis not available",
                "compliance_gaps": "Compliance analysis not available"
            }),
            "report_id": report_id
        })
    except Exception as e:
        logger.error(f"Failed to get AI analysis: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/view-report/<report_id>')
def view_report(report_id):
    try:
        report_id = report_id.split('.')[0]
        json_path = os.path.join(config.reports_dir, report_id, f"{report_id}.json")
        
        if not os.path.exists(json_path):
            return "Report not found", 404
            
        with open(json_path, 'r') as f:
            report_data = json.load(f)

        # Check if PDF exists
        pdf_path = os.path.join(config.reports_dir, report_id, f"{report_id}.pdf")
        format_ext = 'pdf' if os.path.exists(pdf_path) else 'json'
            
        # Format data for template with error handling for AI insights
        template_data = {
            "rfp_name": report_data.get("rfp_name", "Untitled RFP"),
            "date": report_data.get("date", datetime.now().strftime('%Y-%m-%d %H:%M')),
            "eligible": report_data.get("eligible", False),
            "scores": report_data.get("scores", {
                "overall_score": 0,
                "technical_match": 0,
                "requirement_coverage": 0,
                "category_scores": {
                    "technical": 0,
                    "compliance": 0,
                    "business": 0,
                    "experience": 0
                }
            }),
            "conditions": {
                "technical_match": report_data.get("scores", {}).get("category_scores", {}).get("technical", 0) > 70,
                "coverage_sufficient": report_data.get("scores", {}).get("category_scores", {}).get("compliance", 0) > 75
            },
            "ai_insights": report_data.get("ai_insights", {
                "required_qualifications": "Analysis not available",
                "risk_assessment": "Risk analysis not available",
                "compliance_gaps": "Compliance analysis not available"
            }),
            "format_requirements": report_data.get("format_requirements", {
                "document_specs": {},
                "submission_requirements": [],
                "compliance_checklist": []
            }),
            "compliance_analysis": report_data.get("compliance_analysis", {
                "checklist": [],
                "risks": []
            }),
            "checklist": report_data.get("checklist", [])[:3],
            "qualifications": report_data.get("qualifications", [])[:3],
            "report_id": report_id,
            "download_url": f"/download/{report_id}.{format_ext}",
            "share_url": f"/share/{report_id}"
        }
        
        return render_template('report_template.html', **template_data)
        
    except Exception as e:
        logger.error(f"Failed to view report: {str(e)}")
        return str(e), 500

@app.route('/download/<report_id>')
def download_report(report_id):
    try:
        report_id = report_id.split('.')[0]
        
        # Try PDF first, fall back to JSON
        pdf_path = os.path.join(config.reports_dir, report_id, f"{report_id}.pdf")
        if (os.path.exists(pdf_path)):
            return send_file(
                pdf_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f"{report_id}.pdf"
            )
            
        # Fall back to JSON
        json_path = os.path.join(config.reports_dir, report_id, f"{report_id}.json")
        if os.path.exists(json_path):
            return send_file(
                json_path,
                mimetype='application/json',
                as_attachment=True,
                download_name=f"{report_id}.json"
            )
            
        return "Report not found", 404
            
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return str(e), 500

@app.route('/share/<report_id>')
def share_report(report_id):
    try:
        report_id = report_id.split('.')[0]  # Remove extension
        share_url = config.generate_share_link(report_id)
        
        return jsonify({
            "share_url": share_url,
            "report_id": report_id,
            "expires_in": "24 hours"
        })
            
    except Exception as e:
        logger.error(f"Share failed: {str(e)}", exc_info=True)
        return str(e), 500

if __name__ == '__main__':
    try:
        # Ensure clean startup
        os.makedirs(config.reports_dir, exist_ok=True)
        
        print("\nStarting RFP Analysis Tool...")
        print("Server running at http://127.0.0.1:8000")
        print("Press CTRL+C to quit\n")
        
        app.run(
            host='127.0.0.1',
            port=8000,
            debug=True,
            use_reloader=False
        )
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
    finally:
        cleanup_resources()
