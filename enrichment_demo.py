"""Built-in fictional transport for the same real-employee enrichment engine.

The flag selecting this provider never marks an arbitrary person as fictional:
only regenerated demo.py fixture records and their reserved .invalid URLs exist.
Original version-one fixtures and cleanup fingerprints remain unchanged.
"""
from copy import deepcopy
from datetime import datetime, timezone

from crawler.models import PageDocument
from demo import DEMO_DATASET, demo_pages
from enrichment_sources import SourceError, build_query
from extractor import Extractor


ROLE_PROFILES = {
    'Engineering Director': {'skills': ['Engineering leadership', 'Systems architecture'], 'credential': 'Engineering Leadership', 'interest': 'Cycling', 'prior_role': 'Senior Software Engineer'},
    'Software Engineer': {'skills': ['Software engineering', 'Technical writing'], 'credential': 'Backend Systems', 'interest': 'Chess', 'prior_role': 'Junior Developer'},
    'Product Designer': {'skills': ['UX design', 'Design systems'], 'credential': 'Product Design', 'interest': 'Photography', 'prior_role': 'UX Designer'},
    'Security Engineer': {'skills': ['Security engineering', 'Threat modelling'], 'credential': 'Cybersecurity', 'interest': 'Running', 'prior_role': 'Systems Administrator'},
    'Product Manager': {'skills': ['Product strategy', 'Stakeholder management'], 'credential': 'Product Management', 'interest': 'Reading', 'prior_role': 'Product Coordinator'},
    'Data Engineer': {'skills': ['Data engineering', 'Data pipelines'], 'credential': 'Analytics Engineering', 'interest': 'Hiking', 'prior_role': 'Data Analyst'},
    'Operations Manager': {'skills': ['Operations management', 'Process improvement'], 'credential': 'Operations Management', 'interest': 'Gardening', 'prior_role': 'Operations Coordinator'},
    'Research Lead': {'skills': ['Research methods', 'Team leadership'], 'credential': 'Applied Research', 'interest': 'Reading', 'prior_role': 'Senior Researcher'},
    'Platform Engineer': {'skills': ['Platform engineering', 'Cloud infrastructure'], 'credential': 'Cloud Platforms', 'interest': 'Cycling', 'prior_role': 'Systems Engineer'},
    'People Partner': {'skills': ['People operations', 'Employee relations'], 'credential': 'Human Resources', 'interest': 'Cooking', 'prior_role': 'HR Coordinator'},
    'Customer Success Lead': {'skills': ['Customer success', 'Account management'], 'credential': 'Customer Success', 'interest': 'Travel', 'prior_role': 'Customer Success Manager'},
    'Technical Advisor': {'skills': ['Technical advisory', 'Solution architecture'], 'credential': 'Solutions Consulting', 'interest': 'Chess', 'prior_role': 'Solutions Engineer'},
    'Managing Director': {'skills': ['Business leadership', 'Strategic planning'], 'credential': 'Executive Leadership', 'interest': 'Tennis', 'prior_role': 'General Manager'},
    'Consultant': {'skills': ['Management consulting', 'Client advisory'], 'credential': 'Consulting', 'interest': 'Travel', 'prior_role': 'Business Analyst'},
    'Research Analyst': {'skills': ['Data analysis', 'Research methods'], 'credential': 'Research Analysis', 'interest': 'Puzzles', 'prior_role': 'Research Assistant'},
    'Independent Researcher': {'skills': ['Independent research', 'Technical writing'], 'credential': 'Research', 'interest': 'Reading', 'prior_role': 'Research Associate'},
}
_DEFAULT_ROLE_PROFILE = {'skills': ['Business operations', 'Project coordination'], 'credential': 'Business Operations', 'interest': 'Music', 'prior_role': 'Coordinator'}


def role_profile(title):
    """A role-appropriate skills/credential/interest/prior-role set for a fixture job title."""
    return ROLE_PROFILES.get(title, _DEFAULT_ROLE_PROFILE)


class DemoSources:
    def __init__(self, dataset=DEMO_DATASET):
        self.dataset = dataset
        self._pages = {}
        self._seeds = []
        self._search = {}
        for original in demo_pages(dataset):
            page = deepcopy(original)
            for number, person in enumerate(page.structured_data[0]['@graph']):
                url = person['url']
                person['workLocation'] = {'@type': 'Place', 'name': 'Adelaide office', 'address': {
                    '@type': 'PostalAddress', 'addressLocality': 'Adelaide', 'addressCountry': 'Australia'}}
                # Explicit business publication: the legacy v1 top-level contact
                # remains unchanged, while this fixture supplies its purpose.
                person['contactPoint'] = {'@type': 'ContactPoint', 'contactType': 'business',
                    'email': person['email'], 'telephone': person['telephone']}
                profile = role_profile(person.get('jobTitle', ''))
                person['hasCredential'] = {'@type': 'EducationalOccupationalCredential',
                                           'name': f"Fictional Professional Certificate in {profile['credential']}"}
                person['skills'] = list(profile['skills'])
                person['knowsAbout'] = list(profile['skills'])
                person['interests'] = [profile['interest']]
                person['image'] = f'{url}/portrait.png'
                self._pages[url] = self._person_page(url, person)
                for profile in person.get('sameAs', []):
                    self._pages[profile] = self._person_page(profile, person)
                works_for = person.get('worksFor', [])
                organisations = works_for if isinstance(works_for, list) else [works_for]
                company = organisations[0]['name'] if organisations else ''
                entries = [{'url': url, 'source_name': 'Fictional employer profile'}]
                if person['name'] == 'Alex Morgan':
                    # A consistent external match still requires review because
                    # the employer did not link it. It is never merged by name.
                    external = f'https://profiles.corporatemapper.invalid/{dataset}/alex-morgan'
                    external_person = deepcopy(person)
                    external_person['@id'] = external
                    external_person['url'] = external
                    external_person['sameAs'] = []
                    external_person['jobTitle'] = 'Principal Engineer'
                    self._pages[external] = self._person_page(external, external_person)
                    entries.append({'url': external, 'source_name': 'Fictional independent profile'})
                self._search[build_query(person['name'], company)] = entries
            self._pages[page.url] = page
            self._seeds.extend(Extractor(None).extract(page))

    @staticmethod
    def _person_page(url, person):
        record = deepcopy(person)
        return PageDocument(url=url, final_url=url, status_code=200, content_type='text/html',
                            fetched_at=datetime(2026, 9, 27, tzinfo=timezone.utc), html='',
                            title='Fictional demonstration profile',
                            structured_data=[{'@context': 'https://schema.org', '@graph': [record]}])

    def check_search_ready(self):
        pass

    def search(self, name: str, company: str = '') -> list[dict]:
        query = build_query(name, company)
        if query not in self._search:
            raise SourceError('Demo search accepts only the built-in fictional employee fixtures.')
        return deepcopy(self._search[query])

    def fetch(self, url: str) -> PageDocument:
        if url not in self._pages:
            raise SourceError('Demo fetch accepts only built-in fictional source URLs.')
        return deepcopy(self._pages[url])

    def seeds(self) -> list[dict]:
        return deepcopy(self._seeds)

    def close(self):
        pass
