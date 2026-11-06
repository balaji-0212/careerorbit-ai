"""ATS-compliant single-column PDF resume generator using ReportLab."""
import re
from pathlib import Path
from typing import Dict, Any
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from careerorbit.resumes.file_output import reserve_unique_output

class ATSPdfResumeBuilder:
    """Builds clean, single-column ATS-friendly PDF resumes."""

    @staticmethod
    def sanitize_filename_part(text: str) -> str:
        s = re.sub(r'[^a-zA-Z0-9]', '_', text)
        return re.sub(r'_+', '_', s).strip('_')

    def generate_pdf(
        self,
        tailored_data: Dict[str, Any],
        company_name: str,
        role_title: str,
        output_dir: Path
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        comp_clean = self.sanitize_filename_part(company_name)
        role_clean = self.sanitize_filename_part(role_title)
        candidate = self.sanitize_filename_part(tailored_data.get("full_name") or "Candidate")
        filename = f"{candidate}_{comp_clean}_{role_clean}_Resume.pdf"
        output_path = reserve_unique_output(output_dir / filename)

        # 0.45 inch margins for clean standard page fill
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=34,
            rightMargin=34,
            topMargin=28,
            bottomMargin=28
        )

        styles = getSampleStyleSheet()

        # Custom ATS Styles
        name_style = ParagraphStyle(
            'ATS_Name',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#111827')
        )
        contact_style = ParagraphStyle(
            'ATS_Contact',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=11,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#374151')
        )
        section_heading = ParagraphStyle(
            'ATS_SectionHeading',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor('#1E3A8A'),
            spaceBefore=6,
            spaceAfter=2,
            textTransform='uppercase'
        )
        body_style = ParagraphStyle(
            'ATS_Body',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor('#1F2937')
        )
        subheading_style = ParagraphStyle(
            'ATS_Subheading',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#111827')
        )
        bullet_style = ParagraphStyle(
            'ATS_Bullet',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8.2,
            leading=10.8,
            leftIndent=12,
            textColor=colors.HexColor('#1F2937')
        )

        story = []

        # Header
        story.append(Paragraph(str(tailored_data.get("full_name") or "Candidate"), name_style))
        story.append(Spacer(1, 2))
        personal = tailored_data.get("personal", {})
        contact_line = " | ".join(str(personal[key]).strip() for key in ("location", "phone", "email", "linkedin", "github") if personal.get(key))
        if contact_line:
            story.append(Paragraph(contact_line, contact_style))
        story.append(Spacer(1, 4))
        story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor('#9CA3AF'), spaceBefore=2, spaceAfter=4))

        # 1. Professional Summary
        story.append(Paragraph("PROFESSIONAL SUMMARY", section_heading))
        story.append(Paragraph(tailored_data["professional_summary"], body_style))
        story.append(Spacer(1, 4))

        # 2. Technical Skills
        story.append(Paragraph("TECHNICAL SKILLS", section_heading))
        for group, items in tailored_data["key_skills"].items():
            skill_text = f"<b>{group}:</b> {items}"
            story.append(Paragraph(skill_text, body_style))
        story.append(Spacer(1, 4))

        # 3. Professional Experience
        story.append(Paragraph("PROFESSIONAL EXPERIENCE", section_heading))
        for emp in tailored_data["employment"]:
            header_text = f"<b>{emp['employer']}</b> &mdash; <i>{emp['role']}</i> ({emp.get('location', '')}) <font color='#4B5563'>[{emp['start_date']} &ndash; {emp['end_date']}]</font>"
            story.append(Paragraph(header_text, subheading_style))
            for bullet in emp["highlights"]:
                story.append(Paragraph(f"&bull; {bullet}", bullet_style))
            story.append(Spacer(1, 3))

        # 4. Projects
        story.append(Paragraph("PROJECTS", section_heading))
        for proj in tailored_data["ordered_projects"][:3]:  # Top 3 most relevant
            tech_str = ", ".join(proj["technologies"])
            proj_header = f"<b>{proj['name']}</b> <font color='#4B5563'>[{proj['timeline']}]</font><br/><i>Technologies: {tech_str}</i>"
            story.append(Paragraph(proj_header, subheading_style))
            for bullet in proj["highlights"]:
                story.append(Paragraph(f"&bull; {bullet}", bullet_style))
            story.append(Spacer(1, 2))

        # 5. Education
        story.append(Paragraph("EDUCATION", section_heading))
        edu = tailored_data["education"]
        edu_text = f"<b>{edu['institution']}</b><br/>{edu['degree']} in {edu['field_of_study']} &mdash; Graduated {edu['graduation_month']} {edu['graduation_year']} (CGPA: {edu['cgpa']})"
        story.append(Paragraph(edu_text, body_style))
        story.append(Spacer(1, 4))

        # 6. Certifications & Achievements
        story.append(Paragraph("CERTIFICATIONS & ACHIEVEMENTS", section_heading))
        certs_list = [f"{c['name']} ({c['issuer']})" for c in tailored_data["certifications"][:4]]
        story.append(Paragraph(f"&bull; <b>Certifications:</b> {'; '.join(certs_list)}", bullet_style))
        doc.build(story)
        return output_path
