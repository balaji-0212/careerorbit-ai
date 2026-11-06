"""ATS-compliant DOCX resume generator using python-docx."""
import re
from pathlib import Path
from typing import Dict, Any
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from careerorbit.resumes.file_output import reserve_unique_output

class ATSDocxResumeBuilder:
    """Builds clean, ATS-compliant Microsoft Word (.docx) resumes."""

    @staticmethod
    def sanitize_filename_part(text: str) -> str:
        s = re.sub(r'[^a-zA-Z0-9]', '_', text)
        return re.sub(r'_+', '_', s).strip('_')

    def generate_docx(
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
        filename = f"{candidate}_{comp_clean}_{role_clean}_Resume.docx"
        output_path = reserve_unique_output(output_dir / filename)

        doc = docx.Document()

        # Set 0.5 inch margins
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.45)
            section.bottom_margin = Inches(0.45)
            section.left_margin = Inches(0.5)
            section.right_margin = Inches(0.5)

        # Header: Name
        title_p = doc.add_paragraph()
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        candidate_name = tailored_data.get("full_name") or "Candidate"
        run = title_p.add_run(f"{candidate_name.upper()}\n")
        run.bold = True
        run.font.name = "Calibri"
        run.font.size = Pt(17)
        run.font.color.rgb = RGBColor(17, 24, 39)

        # Contact line
        contact_p = doc.add_paragraph()
        contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        personal = tailored_data.get("personal", {})
        contact = " | ".join(str(personal[key]).strip() for key in ("location", "phone", "email", "linkedin", "github") if personal.get(key))
        c_run = contact_p.add_run(contact)
        c_run.font.name = "Calibri"
        c_run.font.size = Pt(9.5)
        c_run.font.color.rgb = RGBColor(75, 85, 99)

        def add_heading(text: str):
            h = doc.add_paragraph()
            h.paragraph_format.space_before = Pt(8)
            h.paragraph_format.space_after = Pt(2)
            r = h.add_run(text.upper())
            r.bold = True
            r.font.name = "Calibri"
            r.font.size = Pt(11)
            r.font.color.rgb = RGBColor(30, 58, 138)

        # 1. Professional Summary
        add_heading("Professional Summary")
        sum_p = doc.add_paragraph()
        sum_p.paragraph_format.space_after = Pt(4)
        s_run = sum_p.add_run(tailored_data["professional_summary"])
        s_run.font.name = "Calibri"
        s_run.font.size = Pt(9.5)

        # 2. Technical Skills
        add_heading("Technical Skills")
        for group, skills_str in tailored_data["key_skills"].items():
            sk_p = doc.add_paragraph()
            sk_p.paragraph_format.space_after = Pt(2)
            g_run = sk_p.add_run(f"{group}: ")
            g_run.bold = True
            g_run.font.name = "Calibri"
            g_run.font.size = Pt(9.5)
            val_run = sk_p.add_run(skills_str)
            val_run.font.name = "Calibri"
            val_run.font.size = Pt(9.5)

        # 3. Professional Experience
        add_heading("Professional Experience")
        for emp in tailored_data["employment"]:
            emp_p = doc.add_paragraph()
            emp_p.paragraph_format.space_before = Pt(4)
            emp_p.paragraph_format.space_after = Pt(1)
            e_run = emp_p.add_run(f"{emp['employer']} — {emp['role']}")
            e_run.bold = True
            e_run.font.name = "Calibri"
            e_run.font.size = Pt(10)
            
            d_run = emp_p.add_run(f" ({emp.get('location', '')}) [{emp['start_date']} – {emp['end_date']}]")
            d_run.italic = True
            d_run.font.name = "Calibri"
            d_run.font.size = Pt(9)
            d_run.font.color.rgb = RGBColor(107, 114, 128)

            for hl in emp["highlights"]:
                b_p = doc.add_paragraph(style='List Bullet')
                b_p.paragraph_format.space_after = Pt(1)
                b_run = b_p.add_run(hl)
                b_run.font.name = "Calibri"
                b_run.font.size = Pt(9.5)

        # 4. Projects
        add_heading("Key Projects")
        for proj in tailored_data["ordered_projects"][:3]:
            pr_p = doc.add_paragraph()
            pr_p.paragraph_format.space_before = Pt(3)
            pr_p.paragraph_format.space_after = Pt(1)
            p_run = pr_p.add_run(proj["name"])
            p_run.bold = True
            p_run.font.name = "Calibri"
            p_run.font.size = Pt(9.5)
            
            p_date = pr_p.add_run(f" [{proj['timeline']}]\nTechnologies: {', '.join(proj['technologies'])}")
            p_date.italic = True
            p_date.font.name = "Calibri"
            p_date.font.size = Pt(9)
            p_date.font.color.rgb = RGBColor(75, 85, 99)

            for hl in proj["highlights"]:
                b_p = doc.add_paragraph(style='List Bullet')
                b_p.paragraph_format.space_after = Pt(1)
                b_run = b_p.add_run(hl)
                b_run.font.name = "Calibri"
                b_run.font.size = Pt(9.5)

        # 5. Education
        add_heading("Education")
        edu = tailored_data["education"]
        edu_p = doc.add_paragraph()
        edu_p.paragraph_format.space_after = Pt(4)
        inst_run = edu_p.add_run(f"{edu['institution']}\n")
        inst_run.bold = True
        inst_run.font.name = "Calibri"
        inst_run.font.size = Pt(9.5)
        deg_run = edu_p.add_run(
            f"{edu['degree']} in {edu['field_of_study']} — Graduated {edu['graduation_month']} {edu['graduation_year']} (CGPA: {edu['cgpa']})"
        )
        deg_run.font.name = "Calibri"
        deg_run.font.size = Pt(9.5)

        # 6. Certifications & Achievements
        add_heading("Certifications & Achievements")
        certs = [f"{c['name']} ({c['issuer']})" for c in tailored_data["certifications"][:4]]
        c_p = doc.add_paragraph(style='List Bullet')
        c_run = c_p.add_run(f"Certifications: {'; '.join(certs)}")
        c_run.font.name = "Calibri"
        c_run.font.size = Pt(9.5)

        doc.save(str(output_path))
        return output_path
