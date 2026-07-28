void arrivalCutoff()
{/*ALCODESTART::1785091093775*/
travellerSource.arrival.reset();
travellerSource.reschedule.reset();
arrivals_closed = true;
completed_at_cutoff = completed;
security_queue_at_cutoff = security_queue_count;
security_in_service_at_cutoff = security_in_service_count;
immigration_queue_at_cutoff = immigration_queue_count;
immigration_in_service_at_cutoff = immigration_in_service_count;
/*ALCODEEND*/}

