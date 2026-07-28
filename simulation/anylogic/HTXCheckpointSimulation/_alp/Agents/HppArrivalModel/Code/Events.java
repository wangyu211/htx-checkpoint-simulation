void arrivalCutoff()
{/*ALCODESTART::1785093300001*/
travellerSource.set_rate( 0.0, PER_SECOND );
arrivals_closed = true;
admitted_at_cutoff = arrival_times.size();
completed_at_cutoff = completed;
finishSimulation();
/*ALCODEEND*/}

