/* SERVICE_VARIABILITY_BEGIN
 * Independent service streams preserve the HPP arrival stream.  Positive-CV
 * arms use a mean-preserving lognormal sensitivity assumption; they are not
 * presented as a fitted site distribution.
 */
private void initializePrimaryServiceRandomStreams() {
	security_service_rng = new java.util.Random(
		service_seed ^ 0x13579BDF2468ACE1L
	);
	immigration_service_rng = new java.util.Random(
		service_seed ^ 0x2468ACE113579BDFL
	);
}

private double nextExplicitStandardNormal( java.util.Random rng ) {
	if ( rng == null )
		throw new IllegalStateException( "service RNG is not initialized" );
	double u1 = rng.nextDouble();
	while ( !( u1 > 0.0 ) ) u1 = rng.nextDouble();
	double u2 = rng.nextDouble();
	return Math.sqrt( -2.0 * Math.log( u1 ) )
		* Math.cos( 2.0 * Math.PI * u2 );
}

private double primaryServiceDemand(
	String distribution,
	double meanSeconds,
	double coefficientOfVariation,
	java.util.Random rng
) {
	if ( !( meanSeconds > 0.0 ) || !Double.isFinite( meanSeconds ) )
		throw new IllegalArgumentException(
			"primary service mean must be positive and finite"
		);
	if ( "FIXED".equals( distribution ) ) {
		if ( coefficientOfVariation != 0.0 )
			throw new IllegalArgumentException(
				"FIXED primary service requires CV=0"
			);
		return meanSeconds;
	}
	if ( !"LOGNORMAL_MEAN_CV".equals( distribution )
		|| !( coefficientOfVariation > 0.0 )
		|| coefficientOfVariation > 2.0
		|| !Double.isFinite( coefficientOfVariation ) )
		throw new IllegalArgumentException(
			"LOGNORMAL_MEAN_CV requires finite 0<CV<=2"
		);
	double sigmaSquared = Math.log(
		1.0 + coefficientOfVariation * coefficientOfVariation
	);
	double sigma = Math.sqrt( sigmaSquared );
	double latentZ = nextExplicitStandardNormal( rng );
	double demand = meanSeconds * Math.exp(
		-0.5 * sigmaSquared + sigma * latentZ
	);
	if ( !( demand > 0.0 ) || !Double.isFinite( demand ) )
		throw new IllegalStateException(
			"sampled primary service demand is not positive and finite"
		);
	return demand;
}
/* SERVICE_VARIABILITY_END */

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
