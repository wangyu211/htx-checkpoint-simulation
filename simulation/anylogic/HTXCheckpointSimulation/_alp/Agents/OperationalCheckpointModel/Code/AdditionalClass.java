/* PRESENTATION_ONLY_BEGIN
 * Deterministic DES-state animation.  These methods only relocate the
 * presentation of agents already held by the Process Modeling Library.
 * They do not add model time, events, random draws, or process blocks.
 */
private void placePresentationAgent(
	OperationalTraveller traveller,
	double baseX,
	double baseY,
	int index
) {
	if ( !presentation_animation_enabled ) return;
	final int iconLimit = 25;
	if ( index < 0 || index >= iconLimit ) {
		traveller.jumpTo( -1000.0, -1000.0 );
		return;
	}
	traveller.jumpTo(
		baseX + 15.0 * ( index % 5 ),
		baseY + 15.0 * ( index / 5 )
	);
}

private void refreshPresentationAnimation() {
	if ( !presentation_animation_enabled ) return;
	for ( int i = 0; i < securityService.queueSize(); i++ )
		placePresentationAgent(
			(OperationalTraveller) securityService.queueGet( i ),
			225.0, 320.0, i
		);
	for ( int i = 0; i < securityService.delaySize(); i++ )
		placePresentationAgent(
			(OperationalTraveller) securityService.delayGet( i ),
			375.0, 320.0, i
		);
	for ( int i = 0; i < immigrationService.queueSize(); i++ )
		placePresentationAgent(
			(OperationalTraveller) immigrationService.queueGet( i ),
			505.0, 320.0, i
		);
	for ( int i = 0; i < immigrationService.delaySize(); i++ )
		placePresentationAgent(
			(OperationalTraveller) immigrationService.delayGet( i ),
			655.0, 320.0, i
		);
}
/* PRESENTATION_ONLY_END */
