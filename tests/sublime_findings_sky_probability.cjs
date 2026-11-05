const assert=require('node:assert/strict');
const {test}=require('node:test');
const {skyCoordinates,probabilityLogit}=require('../mocaviz/static/sublime_findings.js');

// Astropy ICRS -> Galactic / BarycentricMeanEcliptic(equinox=J2000), degrees.
const references=[
  [0,0,96.33728336969006,-60.188551946914465,0.0000018848594922608164,-0.0000058482058407152255],
  [90,0,206.98913107543058,-11.424490966989568,90.00000442036585,-23.439281338610297],
  [266.4051,-28.936175,0.000053296785079047046,-0.00008200901204109911,266.8396179092303,-5.536322853895112],
  [12.345,-67.89,303.2284965658347,-49.237067373356105,321.2880667276168,-61.88731144422607],
  [359.999,45,113.46311041445976,-16.92387788917082,21.69073281170981,40.448377524419655],
  [0,90,122.93192525541662,27.128252414968,89.99998839583333,66.5607186613889],
];
test('sky coordinate transforms match Astropy across quadrants, the longitude seam and a pole',()=>{
  for(const [ra,dec,gl,gb,el,eb] of references){
    assert.deepEqual(skyCoordinates(ra,dec),[ra,dec]);
    for(const [system,expected] of [['galactic',[gl,gb]],['ecliptic',[el,eb]]]){
      const actual=skyCoordinates(ra,dec,system);
      assert.ok(Math.abs(((actual[0]-expected[0]+540)%360)-180)<1e-8,`${system} longitude at ${ra}, ${dec}`);
      assert.ok(Math.abs(actual[1]-expected[1])<1e-8,`${system} latitude at ${ra}, ${dec}`);
      assert.ok(actual[0]>=0&&actual[0]<360);
      assert.ok(actual[1]>=-90&&actual[1]<=90);
    }
  }
});
test('CNN display stretches both tails, stays ordered and keeps exact endpoints finite',()=>{
  const values=[0,1e-6,1e-4,.01,.1,.5,.9,.99,.9999,1-1e-6,1];
  const positions=values.map(probabilityLogit);
  assert.ok(positions.every(Number.isFinite));
  assert.ok(positions.every((value,i)=>!i||value>=positions[i-1]));
  assert.equal(probabilityLogit(.5),0);
  for(const p of [1e-6,1e-4,.01,.1])assert.ok(Math.abs(probabilityLogit(p)+probabilityLogit(1-p))<1e-9);
  assert.ok(probabilityLogit(.999)-probabilityLogit(.99)>probabilityLogit(.51)-probabilityLogit(.5));
  assert.ok(probabilityLogit(.01)-probabilityLogit(.001)>probabilityLogit(.5)-probabilityLogit(.49));
  assert.equal(probabilityLogit(0),probabilityLogit(1e-6));
  assert.equal(probabilityLogit(1),probabilityLogit(1-1e-6));
  for(const invalid of [-.1,1.1,NaN,Infinity,null,undefined])assert.ok(Number.isNaN(probabilityLogit(invalid)));
});
