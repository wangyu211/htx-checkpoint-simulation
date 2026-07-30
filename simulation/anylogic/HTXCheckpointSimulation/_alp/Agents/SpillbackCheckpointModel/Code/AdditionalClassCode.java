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

/* INTERSTAGE_SPILLBACK_AUDIT_BEGIN
 * Canonical, configuration-independent digests support CRN and exact-replay
 * gates.  Rows are sorted before hashing so the digest does not depend on
 * collection iteration order.
 */
public String sha256CanonicalRows( java.util.List<String> sourceRows ) {
	try {
		java.util.ArrayList<String> rows =
			new java.util.ArrayList<String>( sourceRows );
		java.util.Collections.sort( rows );
		java.security.MessageDigest digest =
			java.security.MessageDigest.getInstance( "SHA-256" );
		for ( String row : rows ) {
			digest.update(
				row.getBytes( java.nio.charset.StandardCharsets.UTF_8 )
			);
			digest.update( (byte) '\n' );
		}
		StringBuilder hexadecimal = new StringBuilder();
		for ( byte value : digest.digest() )
			hexadecimal.append(
				String.format( java.util.Locale.ROOT, "%02x", value & 0xff )
			);
		return hexadecimal.toString();
	} catch ( java.security.NoSuchAlgorithmException exception ) {
		throw new IllegalStateException( "SHA-256 is unavailable", exception );
	}
}
/* INTERSTAGE_SPILLBACK_AUDIT_END */
