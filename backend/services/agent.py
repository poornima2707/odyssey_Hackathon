from groq import Groq
from typing import Dict, Any, List
import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

class RFPRequirementAgent:
    def __init__(self):
        try:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY not found in environment")
            
            self.client = Groq(
                api_key=api_key
            )
            self.model = "mixtral-8x7b-32768"  # Update to supported model
            
            self.format_prompt = """
            Analyze the RFP content and extract all submission formatting requirements:
            
            1. Document Specifications:
               - Page limits
               - Font requirements
               - Margins and spacing
               - Section requirements
            
            2. Required Attachments:
               - Mandatory forms
               - Supporting documents
               - Certifications
            
            3. Submission Guidelines:
               - Table of contents
               - Section ordering
               - Numbering requirements
               - Header/footer specifications
            
            RFP Content:
            {content}
            
            Provide a structured response with specific requirements found.
            """
            
        except Exception as e:
            logger.error(f"RFP Agent initialization failed: {str(e)}")
            raise

    async def extract_format_requirements(self, content: str) -> Dict[str, Any]:
        """Extract formatting requirements from RFP content"""
        try:
            # Direct Groq API call instead of LangChain
            completion = await self.client.chat.completions.create(
                model="mixtral-8x7b-32768",
                messages=[
                    {"role": "system", "content": "You are an expert RFP analyst."},
                    {"role": "user", "content": self.format_prompt.format(content=content)}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            response_text = completion.choices[0].message.content
            return self._parse_format_requirements(response_text)
            
        except Exception as e:
            logger.error(f"Format extraction failed: {str(e)}")
            return self._get_default_requirements()

    def _parse_format_requirements(self, response: str) -> Dict[str, Any]:
        """Parse and structure the AI response"""
        try:
            requirements = {
                "document_specs": {
                    "page_limit": None,
                    "font": None,
                    "spacing": None,
                    "margins": None
                },
                "attachments": [],
                "submission_guidelines": {
                    "toc_required": False,
                    "section_ordering": [],
                    "special_requirements": []
                }
            }
            
            # Extract page limits
            if "page" in response.lower():
                import re
                page_match = re.search(r'(\d+)[\s-]*page', response.lower())
                if page_match:
                    requirements["document_specs"]["page_limit"] = int(page_match.group(1))
            
            # Extract font requirements
            font_keywords = ["font", "times new roman", "arial", "calibri"]
            for line in response.split('\n'):
                if any(keyword in line.lower() for keyword in font_keywords):
                    requirements["document_specs"]["font"] = line.strip()
                    break
            
            # Extract required attachments
            attachment_keywords = ["form", "attachment", "certificate", "document"]
            for line in response.split('\n'):
                if any(keyword in line.lower() for keyword in attachment_keywords):
                    requirements["attachments"].append(line.strip())
            
            # Extract TOC requirement
            if "table of contents" in response.lower() or "toc" in response.lower():
                requirements["submission_guidelines"]["toc_required"] = True
            
            return requirements
            
        except Exception as e:
            logger.error(f"Requirement parsing failed: {str(e)}")
            return {
                "document_specs": {},
                "attachments": [],
                "submission_guidelines": {}
            }

    def _get_default_requirements(self) -> Dict[str, Any]:
        """Return default requirements structure"""
        return {
            "document_specs": {
                "page_limit": None,
                "font": None,
                "spacing": None,
                "margins": None
            },
            "submission_requirements": [],
            "compliance_checklist": [],
            "risk_factors": []
        }

    def validate_formatting(self, document_content: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """Validate if document meets formatting requirements"""
        validation = {
            "meets_requirements": True,
            "issues": []
        }
        
        try:
            # Safe access to nested dictionary
            doc_specs = requirements.get("document_specs", {})
            page_limit = doc_specs.get("page_limit", 0)
            
            if page_limit > 0:  # Only check if limit is specified
                page_count = document_content.count('\f') + 1
                if page_count > page_limit:
                    validation["meets_requirements"] = False
                    validation["issues"].append(
                        f"Document exceeds {page_limit} page limit"
                    )
            
            return validation
            
        except Exception as e:
            logger.error(f"Format validation failed: {str(e)}")
            return {
                "meets_requirements": True,  # Default to true if validation fails
                "issues": []
            }
