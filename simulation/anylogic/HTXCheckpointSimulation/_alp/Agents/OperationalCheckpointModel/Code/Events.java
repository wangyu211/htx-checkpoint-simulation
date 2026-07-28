void arrivalCutoff()
{/*ALCODESTART::1785163143775*/
travellerSource.set_rate( 0.0, PER_SECOND );
// Match the already-verified CheckpointModel cutoff mechanism. Source.RATE
// owns both an arrival timeout and a reschedule timeout; reset both so no
// event already on the calendar can inject a traveller at or after cutoff.
travellerSource.arrival.reset();
travellerSource.reschedule.reset();
arrivals_closed = true;
admitted_at_cutoff = admitted;
completed_at_cutoff = completed;
security_queue_at_cutoff = security_queue_count;
security_in_service_at_cutoff = security_in_service_count;
immigration_queue_at_cutoff = immigration_queue_count;
immigration_in_service_at_cutoff = immigration_in_service_count;
if ( completed == admitted ) {
	run_status = "COMPLETE";
	finishSimulation();
}
/*ALCODEEND*/}
