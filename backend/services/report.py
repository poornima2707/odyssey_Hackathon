import pdfkit
import jinja2
from datetime import datetime
import os
from typing import Dict, Any, List  # Add List to imports
import uuid
from urllib.parse import urljoin
import logging
import json
import shutil
import sys, os
from langchain_core.prompts import PromptTemplate  # Updated import
from groq import Groq
from langchain.chains import LLMChain
import asyncio
from dotenv import load_dotenv  # Add this import

logger = logging.getLogger(__name__)

class ReportGenerator:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        try:
            # Absolute paths for directories
            self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.report_dir = os.path.join(self.base_dir, "reports")
            os.makedirs(self.report_dir, exist_ok=True)
            os.chmod(self.report_dir, 0o777)

            self.template_dir = os.path.join(self.base_dir, "templates")
            os.makedirs(self.template_dir, exist_ok=True)
            
            self.template_loader = jinja2.FileSystemLoader(searchpath=self.template_dir)
            self.template_env = jinja2.Environment(loader=self.template_loader)
            
            # Try multiple wkhtmltopdf paths
            wkhtmltopdf_paths = [
                r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
                r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
                "/usr/local/bin/wkhtmltopdf",
                "/usr/bin/wkhtmltopdf",
                "wkhtmltopdf"  # Try PATH
            ]
            
            self.wkhtmltopdf_path = None
            for path in wkhtmltopdf_paths:
                try:
                    if shutil.which(path):
                        self.wkhtmltopdf_path = path
                        break
                except:
                    continue

            self.pdf_config = pdfkit.configuration(wkhtmltopdf=self.wkhtmltopdf_path) if self.wkhtmltopdf_path else None
            
        except Exception as e:
            logger.error(f"ReportGenerator initialization failed: {str(e)}")
            raise

        # Configure pdfkit options
        self.pdf_options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': "UTF-8",
            'no-outline': None,
            'enable-local-file-access': None
        }
        
        self.base_url = "http://localhost:8000"  # Update with your domain
        self.share_tokens = {}

        # Initialize LangChain templates with Groq-optimized prompts
        self.analysis_prompts = {
            "requirements": PromptTemplate(
                input_variables=["rfp_content"],
                template="""Analyze this RFP and provide structured output:

                1. Required Qualifications:
                - Technical certifications
                - Experience requirements
                - Mandatory skills
                
                2. Compliance Requirements:
                - Regulatory requirements
                - Industry standards
                - Required certifications
                
                3. Risk Assessment:
                - Technical risks
                - Compliance risks
                - Business risks
                
                RFP Content: {rfp_content}
                
                Provide specific, detailed findings for each section."""
            ),
            "compliance_check": PromptTemplate(
                input_variables=["rfp_content", "company_profile"],
                template="""Compare these requirements with company capabilities:

                1. Gap Analysis:
                - Technical gaps (with specific details)
                - Experience gaps (with years/skills)
                - Certification gaps (list missing items)
                
                2. Risk Evaluation:
                - High-risk requirements
                - Missing capabilities
                - Compliance issues
                
                3. Recommendations:
                - Required actions
                - Priority items
                - Timeline considerations
                
                RFP: {rfp_content}
                Company Profile: {company_profile}
                
                Provide detailed analysis with specific examples."""
            )
        }
        
        try:
            # Initialize Groq
            groq_api_key = os.getenv("GROQ_API_KEY")
            if not groq_api_key:
                raise ValueError("GROQ_API_KEY not found in environment")
                
            self.llm = Groq(
                api_key=groq_api_key
            )
            # Update to supported model
            self.model = "llama2-70b"  
            
            # Create LangChain chains without model parameter
            self.analysis_chains = {
                name: LLMChain(
                    llm=self.llm, 
                    prompt=prompt
                )
                for name, prompt in self.analysis_prompts.items()
            }
            logger.info("Groq LLM initialized successfully")
            
        except Exception as e:
            logger.error(f"Groq LLM initialization failed: {str(e)}")
            self.llm = None

    async def _analyze_content(self, rfp_content: str, company_content: str) -> Dict[str, Any]:
        """Perform direct Groq API analysis"""
        try:
            # Direct Groq API calls for better control
            requirements_response = await self.llm.chat.completions.create(
                model="mixtral-8x7b-32768",
                messages=[
                    {"role": "system", "content": "You are an expert RFP analyst"},
                    {"role": "user", "content": self.analysis_prompts["requirements"].format(rfp_content=rfp_content)}
                ],
                temperature=0.1
            )
            
            compliance_response = await self.llm.chat.completions.create(
                model="mixtral-8x7b-32768",
                messages=[
                    {"role": "system", "content": "You are an expert compliance analyst"},
                    {"role": "user", "content": self.analysis_prompts["compliance_check"].format(
                        rfp_content=rfp_content,
                        company_profile=company_content
                    )}
                ],
                temperature=0.1
            )
            
            return {
                "requirements": requirements_response.choices[0].message.content,
                "compliance": compliance_response.choices[0].message.content,
                "risks": self._extract_risks_from_analysis(
                    requirements_response.choices[0].message.content,
                    compliance_response.choices[0].message.content
                )
            }
            
        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}")
            return {}

    def _extract_risks_from_analysis(self, requirements_text: str, compliance_text: str) -> List[str]:
        """Extract risk items from analysis responses"""
        risks = []
        try:
            # Look for risk-related content in both responses
            risk_sections = [
                section for section in requirements_text.split('\n')
                if any(risk_word in section.lower() for risk_word in ["risk", "warning", "critical", "concern"])
            ]
            compliance_risks = [
                section for section in compliance_text.split('\n')
                if any(risk_word in section.lower() for risk_word in ["gap", "missing", "risk", "issue"])
            ]
            
            risks.extend(risk_sections)
            risks.extend(compliance_risks)
            
            return risks[:5]  # Return top 5 most critical risks
            
        except Exception as e:
            logger.error(f"Risk extraction failed: {str(e)}")
            return ["Risk analysis unavailable"]

    def _extract_qualifications(self, analysis_result: Dict[str, Any]) -> list:
        """Extract key qualifications summary"""
        matches = analysis_result.get("matches", [])
        requirements = self._extract_key_requirements(matches)
        
        # Get only critical qualifications
        qualifications = []
        if requirements["technical"]:
            tech_count = len([r for r in requirements["technical"] if r["score"] > 0.7])
            if tech_count > 0:
                qualifications.append({
                    "type": "Technical",
                    "details": f"Meets {tech_count} technical requirements",
                    "met": tech_count / len(requirements["technical"]) > 0.7
                })
                
        if requirements["compliance"]:
            compliance_count = len([r for r in requirements["compliance"] if r["score"] > 0.8])
            qualifications.append({
                "type": "Compliance",
                "details": f"Meets {compliance_count} compliance standards",
                "met": compliance_count == len(requirements["compliance"])
            })
            
        return qualifications[:3]  # Return max 3 key qualifications

    def _extract_key_requirements(self, matches):
        """Extract key requirements from document matches"""
        requirements = {
            "technical": [],
            "compliance": [],
            "business": [],
            "experience": []
        }
        
        keywords = {
            "technical": ["technical", "system", "software", "hardware", "infrastructure", "technology"],
            "compliance": ["comply", "regulation", "standard", "certification", "iso", "requirement"],
            "business": ["cost", "budget", "financial", "payment", "delivery", "timeline"],
            "experience": ["experience", "year", "project", "similar", "previous", "track record"]
        }
        
        for match in matches:
            text = match["rfp_text"].lower()
            score = 1.0 - float(min(match["company_matches"]["distances"]))
            
            for category, terms in keywords.items():
                if any(term in text for term in terms):
                    requirements[category].append({
                        "text": match["rfp_text"],
                        "score": score,
                        "matched": score > 0.7
                    })
        
        return requirements

    def _analyze_risks(self, analysis_result: Dict[str, Any]) -> list:
        """Generate automated risk analysis based on document content"""
        try:
            if not analysis_result:
                return ["No analysis data available"]
                
            risks = []
            requirements = self._extract_key_requirements(analysis_result.get("matches", []))
            scores = analysis_result.get("scores", {})
            
            # Technical risks
            tech_reqs = requirements.get("technical", [])
            if tech_reqs:
                unmet_tech = sum(1 for r in tech_reqs if not r.get("matched", False))
                if unmet_tech / len(tech_reqs) > 0.3:
                    risks.append(f"High Risk: {unmet_tech} technical requirements not adequately met")
            
            return risks or ["No significant risks identified"]
            
        except Exception as e:
            logger.error(f"Risk analysis failed: {str(e)}")
            return ["Risk analysis unavailable"]

    def _generate_checklist(self, analysis_result: Dict[str, Any]) -> list:
        """Generate concise checklist based on key requirements"""
        checklist = []
        requirements = self._extract_key_requirements(analysis_result.get("matches", []))
        scores = analysis_result.get("scores", {})

        # Add only critical missing requirements
        unmet_critical = []
        if requirements["technical"]:
            unmet_tech = [r for r in requirements["technical"] if not r["matched"] and r["score"] < 0.6]
            if unmet_tech:
                unmet_critical.append(f"Address Technical Gaps ({len(unmet_tech)} items)")
                
        if requirements["compliance"]:
            unmet_compliance = [r for r in requirements["compliance"] if not r["matched"]]
            if unmet_compliance:
                unmet_critical.append(f"Complete Compliance Requirements ({len(unmet_compliance)} items)")

        # Return max 3 most important items
        checklist = unmet_critical[:2]
        if scores.get("overall_score", 0) < 75:
            checklist.append("Strengthen Overall Response")
            
        return checklist

    def _calculate_weighted_scores(self, requirements):
        """Calculate weighted scores based on requirement categories"""
        weights = {
            "technical": 0.4,
            "compliance": 0.3,
            "business": 0.2,
            "experience": 0.1
        }
        
        category_scores = {}
        for category, reqs in requirements.items():
            if reqs:
                matched = sum(r["score"] for r in reqs)
                total = len(reqs)
                category_scores[category] = (matched / total) * 100
            else:
                category_scores[category] = 0
        
        overall_score = sum(
            category_scores[cat] * weight 
            for cat, weight in weights.items()
        )
        
        return {
            "overall_score": round(overall_score, 2),
            "category_scores": category_scores
        }

    async def generate_report(self, analysis_result: Dict[str, Any], rfp_name: str) -> Dict[str, Any]:
        """Generate intelligent report with LangChain analysis"""
        try:
            logger.info(f"Generating intelligent report for {rfp_name}")
            
            # Get content for analysis
            rfp_content = "\n".join([m["rfp_text"] for m in analysis_result.get("matches", [])])
            company_content = "\n".join([
                match["company_matches"]["texts"][0] 
                for match in analysis_result.get("matches", [])
            ])
            
            # Perform intelligent analysis
            ai_analysis = await self._analyze_content(rfp_content, company_content)
            
            # Format the AI insights with better structure
            analysis_result.update({
                "ai_insights": {
                    "required_qualifications": self._format_ai_content(ai_analysis.get("requirements", "")),
                    "risk_assessment": self._format_ai_content(ai_analysis.get("risks", "")),
                    "compliance_gaps": self._format_ai_content(ai_analysis.get("compliance", "")),
                },
                "format_requirements": analysis_result.get("format_requirements", {
                    "document_specs": {},
                    "submission_requirements": [],
                    "compliance_checklist": []
                })
            })
            
            # Continue with existing report generation
            requirements = self._extract_key_requirements(analysis_result.get("matches", []))
            scores = self._calculate_weighted_scores(requirements)
            
            analysis_result.update({
                "scores": scores,
                "requirements": requirements,
                "risks": self._analyze_risks(analysis_result),
                "checklist": self._generate_checklist(analysis_result),
                "qualifications": self._extract_qualifications(analysis_result)
            })
            
            # Generate report ID and paths
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_id = f"rfp_analysis_{timestamp}"
            report_dir = os.path.join(self.report_dir, report_id)
            os.makedirs(report_dir, exist_ok=True)
            
            # Generate paths
            json_path = os.path.join(report_dir, f"{report_id}.json")
            pdf_path = os.path.join(report_dir, f"{report_id}.pdf")

            # Save JSON
            with open(json_path, 'w') as f:
                json.dump(analysis_result, f)

            # Try PDF generation
            if self.pdf_config:
                try:
                    template = self.template_env.get_template('report_template.html')
                    html_content = template.render(**analysis_result)
                    pdfkit.from_string(html_content, pdf_path, configuration=self.pdf_config)
                except Exception as e:
                    logger.warning(f"PDF generation failed: {str(e)}")
                    pdf_path = None

            return {
                "report_id": report_id,
                "format": "pdf" if pdf_path and os.path.exists(pdf_path) else "json",
                "path": pdf_path if pdf_path and os.path.exists(pdf_path) else json_path
            }

        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            raise

    def _format_ai_content(self, content: str) -> str:
        """Format AI response content for HTML display"""
        if not content:
            return "Analysis not available"
        
        # Replace newlines with HTML breaks
        content = content.replace('\n', '<br>')
        # Convert basic markdown-style lists to HTML
        content = content.replace('- ', '• ')
        return content

    def get_report_link(self, filepath: str) -> str:
        """Generate shareable link for report"""
        # In a real implementation, this would upload to cloud storage
        # and return a shareable link
        return f"file://{filepath}"

    def get_report_by_id(self, report_id: str) -> str:
        """Get report filepath by ID"""
        return self.share_tokens.get(report_id)

    def cleanup_old_reports(self, max_age_hours: int = 24):
        """Clean up old report files"""
        current_time = datetime.now()
        for filename in os.listdir(self.report_dir):
            filepath = os.path.join(self.report_dir, filename)
            file_age = (current_time - datetime.fromtimestamp(os.path.getctime(filepath))).total_seconds() / 3600
            if file_age > max_age_hours:
                os.remove(filepath)
        
        # Also cleanup old share tokens
        expired_tokens = [token for token, path in self.share_tokens.items() 
                         if not os.path.exists(path)]
        for token in expired_tokens:
            self.share_tokens.pop(token, None)

    async def test_report_generation(self):
        """Test report generation with sample data"""
        sample_analysis = {
            "eligible": True,
            "date": datetime.now().strftime('%Y-%m-%d %H:%M'),
            "rfp_name": "Test RFP",
            "conditions_met": {
                "has_requirements": True,
                "has_high_matches": True,
                "more_high_than_low": True,
                "majority_matched": True
            }
        }
        
        try:
            result = await self.generate_report(
                analysis_result=sample_analysis,
                rfp_name="ELIGIBLE RFP -1.pdf"
            )
            
            if result and result.get("path") and os.path.exists(result["path"]):
                print(f"Test report generated successfully at: {result['path']}")
                return True
                
            return False
        except Exception as e:
            print(f"Report generation test failed: {str(e)}")
            return False

if __name__ == "__main__":
    # Run async test
    import asyncio
    generator = ReportGenerator()
    asyncio.run(generator.test_report_generation())
