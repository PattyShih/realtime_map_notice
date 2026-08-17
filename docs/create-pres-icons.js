// Generate icon PNGs as base64 for embedding in slides
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const sharp = require('sharp');
const fs = require('fs');

const icons = {
  map: require('react-icons/fa').FaMapMarkerAlt,
  warning: require('react-icons/fa').FaExclamationTriangle,
  wifi: require('react-icons/fa').FaWifi,
  server: require('react-icons/fa').FaServer,
  database: require('react-icons/fa').FaDatabase,
  docker: require('react-icons/fa').FaDocker,
  users: require('react-icons/fa').FaUsers,
  comments: require('react-icons/fa').FaComments,
  clock: require('react-icons/fa').FaClock,
  shield: require('react-icons/fa').FaShieldAlt,
  chart: require('react-icons/fa').FaChartBar,
  rocket: require('react-icons/fa').FaRocket,
  bullhorn: require('react-icons/fa').FaBullhorn,
  satellite: require('react-icons/fa').FaSatelliteDish,
  cogs: require('react-icons/fa').FaCogs,
  lock: require('react-icons/fa').FaLock,
  github: require('react-icons/fa').FaGithub,
  envelope: require('react-icons/fa').FaEnvelope,
  check: require('react-icons/fa').FaCheckCircle,
  times: require('react-icons/fa').FaTimesCircle,
  arrow: require('react-icons/fa').FaArrowRight,
  code: require('react-icons/fa').FaCode,
  globe: require('react-icons/fa').FaGlobe,
  layer: require('react-icons/fa').FaLayerGroup,
};

async function iconToBase64(IconComponent, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
  const pngBuffer = await sharp(Buffer.from(svg)).png().toBuffer();
  return 'image/png;base64,' + pngBuffer.toString('base64');
}

async function main() {
  const result = {};
  for (const [name, Icon] of Object.entries(icons)) {
    result[name] = await iconToBase64(Icon, '#FFFFFF', 256);
    result[name + '_teal'] = await iconToBase64(Icon, '#0891B2', 256);
    result[name + '_navy'] = await iconToBase64(Icon, '#1E2761', 256);
    result[name + '_dark'] = await iconToBase64(Icon, '#64748B', 256);
  }
  fs.writeFileSync('docs/icons.json', JSON.stringify(result));
  console.log(`Generated ${Object.keys(result).length} icon variants, saved to docs/icons.json`);
}

main().catch(console.error);
