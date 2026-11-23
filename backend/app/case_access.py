"""Alcance de consulta y de gestión de casos."""

from sqlalchemy import or_, select, true

from .models import Analysis, Case, CaseReader, ClinicalReading, Role, User


def manages_case(case: Case, user: User) -> bool:
    return user.role == Role.admin or case.created_by_id == user.id


def has_read_analysis(user: User):
    return (
        select(ClinicalReading.id)
        .where(ClinicalReading.analysis_id == Analysis.id, ClinicalReading.reader_id == user.id)
        .correlate(Analysis)
        .exists()
    )


def visible_analysis_result(user: User):
    if user.role == Role.admin:
        return true()
    return or_(Case.created_by_id == user.id, has_read_analysis(user))


def visible_cases(query, user: User):
    if user.role == Role.admin:
        return query
    owned = Case.created_by_id == user.id
    if user.role == Role.medico:
        assigned = (
            select(CaseReader.case_id)
            .where(CaseReader.case_id == Case.id, CaseReader.reader_id == user.id)
            .exists()
        )
        return query.where(or_(owned, assigned))
    return query.where(owned)
