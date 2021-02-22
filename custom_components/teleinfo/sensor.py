import logging
import voluptuous as vol
import serial_asyncio
from datetime import timedelta
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (CONF_NAME, CONF_RESOURCES, STATE_UNKNOWN, ATTR_ATTRIBUTION, EVENT_HOMEASSISTANT_STOP)
from homeassistant.util import Throttle


REQUIREMENTS = ['pyserial-asyncio==0.5']
DOMAIN = 'teleinfo'
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)
SENSOR_TYPES = {
	'adco': ['Contrat', '', 'mdi:numeric'],					# N° d’identification du compteur : ADCO(12 caractères)
	'optarif': ['Option tarifaire', '', 'mdi:file-document-edit'],		# Option tarifaire(type d’abonnement) : OPTARIF(4 car.)
	'isousc': ['Intensité souscrite', 'A', 'mdi:information-outline'],  	# Intensité souscrite : ISOUSC( 2 car.unité = ampères)
	'hchc': ['Heures creuses', 'Wh', 'mdi:timelapse'],			# Index heures creuses si option = heures creuses : HCHC( 9 car.unité = Wh)
	'hchp': ['Heures pleines', 'Wh', 'mdi:timelapse'],			# Index heures pleines si option = heures creuses : HCHP( 9 car.unité = Wh)
	'ptec': ['Période Tarifaire', '', 'mdi:clock-outline'],			# Période tarifaire en cours : PTEC( 4 car.)
	'iinst': ['Intensite instantanee', 'A', 'mdi:current-ac'],		# Intensité instantanée : IINST( 3 car.unité = ampères)
	'imax': ['Intensite max', 'A', 'mdi:format-vertical-align-top'],	# Intensité maximale : IMAX( 3 car.unité = ampères)
	'papp': ['Puissance apparente', 'VA', 'mdi:flash'],			# Puissance apparente : PAPP( 5 car.unité = Volt.ampères)
	'hhphc': ['Groupe horaire', '', 'mdi:av-timer'],			# Groupe horaire si option = heures creuses ou tempo : HHPHC(1 car.)
	'motdetat': ['Mot d etat', '', 'mdi:check'],				# Mot d’état(autocontrôle) : MOTDETAT(6 car.)
	'base': ['Base', 'Wh', ''],						# Index si option = base : BASE( 9 car.unité = Wh)
	'ejp hn': ['EJP Heures normales', 'Wh', ''],				# Index heures normales si option = EJP : EJP HN( 9 car.unité = Wh)</para>
	'ejp hpm': ['EJP Heures de pointe', 'Wh', ''],				# Index heures de pointe mobile si option = EJP : EJP HPM( 9 car.unité = Wh)</para>
	'pejp': ['EJP Préavis', 'Wh', ''],					# Préavis EJP si option = EJP : PEJP( 2 car.) 30mn avant période EJP</para>
	'bbr hc jb': ['Tempo heures bleues creuses', 'Wh', ''],			# Index heures creuses jours bleus si option = tempo : BBR HC JB( 9 car.unité = Wh)</para>
	'bbr hp jb': ['Tempo heures bleues pleines', 'Wh', ''],			# Index heures pleines jours bleus si option = tempo : BBR HP JB( 9 car.unité = Wh)</para>
	'bbr hc jw': ['Tempo heures blanches creuses', 'Wh', ''],		# Index heures creuses jours blancs si option = tempo : BBR HC JW( 9 car.unité = Wh)</para>
	'bbr hp jw': ['Tempo heures blanches pleines', 'Wh', ''],		# Index heures pleines jours blancs si option = tempo : BBR HP JW( 9 car.unité = Wh)</para>
	'bbr hc jr': ['Tempo heures rouges creuses', 'Wh', ''],			# Index heures creuses jours rouges si option = tempo : BBR HC JR( 9 car.unité = Wh)</para>
	'bbr hp jr': ['Tempo heures rouges pleines', 'Wh', ''],			# Index heures pleines jours rouges si option = tempo : BBR HP JR( 9 car.unité = Wh)</para>
	'demain': ['Tempo couleur demain', '', ''],				# Couleur du lendemain si option = tempo : DEMAIN</para>
	'adps': ['Dépassement Puissance', '', ''],				# Avertissement de dépassement de puissance souscrite : ADPS( 3 car.unité = ampères) (message émis uniquement en cas de dépassement effectif, dans ce cas il est immédiat)</para>
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
	vol.Required(CONF_RESOURCES, default=[]):
		vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)])
})

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
	"""Setup sensors"""
	DATA = TeleinfoData(hass)
	entities = []

	hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, DATA.stop_serial_read())
	for resource in config[CONF_RESOURCES]:
		sensor_type = resource.lower()

		if sensor_type not in SENSOR_TYPES:
			_LOGGER.warning("Sensor type: %s does not appear in teleinfo", sensor_type)

		entities.append(TeleinfoSensor(DATA, sensor_type))

	async_add_entities(entities)

class TeleinfoSensor(Entity):
	"""Implementation of the Teleinfo sensor."""

	def __init__(self, data, sensor_type):
		"""Initialize the sensor."""
		self._type = sensor_type
		self._name = SENSOR_TYPES[sensor_type][0]
		self._unit = SENSOR_TYPES[sensor_type][1]
		self._state = STATE_UNKNOWN
		self.data = data

	async def async_added_to_hass(self):
		"""Handle when an entity is about to be added to Home Assistant."""
		_LOGGER.info('Initialize sensor %s', self._type)
		self.data.initialize_reading()

	@property
	def name(self):
		"""Return the name of the sensor."""
		return self._name

	@property
	def icon(self):
		"""Icon to use in the frontend, if any."""
		return SENSOR_TYPES[self._type][2]

	@property
	def state(self):
		"""Return the state of the sensor."""
		return self._state

	@property
	def unit_of_measurement(self):
		"""Return the unit of measurement of this entity, if any."""
		return self._unit

	def update(self):
		"""Get the latest data from device and updates the state."""
		if not self.data.frame:
			_LOGGER.warn("no data from teleinfo!")
			return
		val = self.data.frame[self._type.upper()]
		if not val:
			_LOGGER.warn("no data for %s", self._type.upper())
			return

		if val.isdigit():
			self._state = int(val)
		else:
			self._state = val

class TeleinfoData:
	"""Stores the data retrieved from Teleinfo.
	For each entity to use, acts as the single point responsible for fetching
	updates from the server.
	"""

	def __init__(self, hass):
		"""Initialize the data object."""
		self._frame = {}
		self._serial_loop_task = None
		self._hass = hass

	@property
	def frame(self):
		"""Get latest update if throttle allows. Return status."""
		return self._frame

	def initialize_reading(self):
		"""Register read task to home assistant"""
		if self._serial_loop_task:
			_LOGGER.warn('task already initialized')
			return

		_LOGGER.info('Initialize teleinfo task')
		self._serial_loop_task = self._hass.loop.create_task(
			self.serial_read("/dev/ttyUSB0", baudrate=1200, bytesize=7, parity='E', stopbits=1, rtscts=1))

	async def serial_read(self, device, **kwargs):
		"""Process the serial data."""
		_LOGGER.debug(u"Initializing Teleinfo")
		reader, _ = await serial_asyncio.open_serial_connection(url=device, **kwargs)
		is_over = True

		# First read need to clear the grimlins.
		line = await reader.readline()

		while True:
			line = await reader.readline()
			line = line.decode('ascii').replace('\r', '').replace('\n', '')

			if is_over and ('\x02' in line):
				is_over = False
				_LOGGER.debug(" Start Frame")
				continue

			if (not is_over) and ('\x03' not in line):
				name, value = line.split()[0:2]
				_LOGGER.debug(" Got : [%s] =  (%s)", name, value)
				self._frame[name] = value

			if (not is_over) and ('\x03' in line):
				is_over = True
				_LOGGER.debug(" End Frame")
				continue

	async def stop_serial_read(self):
		"""Close resources."""
		if self._serial_loop_task:
			self._serial_loop_task.cancel()

