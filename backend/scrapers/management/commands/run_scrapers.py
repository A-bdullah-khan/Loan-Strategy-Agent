from django.core.management.base import BaseCommand

from scrapers.bank_scraper import run_all_scrapers


class Command(BaseCommand):
    help = 'Run the live scrapers for all 13 banks and sync results into the database.'

    def handle(self, *args, **options):
        self.stdout.write('Running live bank scrapers...')
        result = run_all_scrapers()
        self.stdout.write(self.style.SUCCESS(
            f"Done — banks processed: {result['banks_processed']} "
            f"({result['banks_rejected']} rejected), "
            f"policies created: {result['policies_created']}, "
            f"policies updated: {result['policies_updated']}, "
            f"policies rejected: {result['policies_rejected']}"
        ))
