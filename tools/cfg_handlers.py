import prototext

UNRULY_BUILDERS =[
  'V8 Linux64 - builder',
  'V8 Linux64 - debug builder',
  'V8 Fuchsia - builder',
]

class BuildBucketCfg:
  def __init__(self):
    self.cfg = prototext.prototext2dict('cr-buildbucket.cfg')
    

  def buckets(self):
    return self.cfg['buckets']

  def mixins(self):
    return self.to_map(self.cfg['builder_mixins'], 'name')

  def to_map(self, lst, key):
    return dict([(item[key][0], item) for item in lst])

  def builder_name(self, builder):
    return builder['name'][0]

  def builders(self, bucket):
    return bucket['swarming'][0]['builders']

  def stable_builders(self):
    stable_bucket = self.get_bucket_by_suffix('stable')
    result = []
    for builder in self.builders(stable_bucket):
      if self.builder_name(builder) not in UNRULY_BUILDERS:
        result.append(builder)
    return result

  def properties(self, builder):
    props = dict()
    recipe = self.consolidate_recipe(builder.get('recipe',[]))
    if 'properties' in recipe:
      self.add_props(props, recipe['properties'])
    if 'properties_j' in recipe:
      self.add_props(props, recipe['properties_j'])
    return props

  def dimensions(self, builder):
    dims = builder.get('dimensions', [])
    dim_dict = dict()
    for item in dims:
      splited = item.split(":", 1)
      dim_dict[splited[0]] = splited[1]
    return dim_dict

  def recipe_name(self, recipe):
    return recipe.get('name',[None])[-1]

  def cipd_package(self, recipe):
    return recipe.get('cipd_package',[None])[-1]

  def cipd_version(self, recipe):
    return recipe.get('cipd_version',[None])[-1]

  def get_bucket_by_suffix(self, suffix):
    for bucket in self.buckets():
      if bucket['name'][0].endswith(suffix):
        return bucket

  def trytriggered_builders_timeouts(self):
    result = dict()
    triggered_bucket = self.get_bucket_by_suffix('triggered')
    for builder in self.builders(triggered_bucket):
      if self.builder_name(builder).endswith('_ng_triggered'):
        if 'execution_timeout_secs' in builder:
          result[self.builder_name(builder)[:-13]] = builder['execution_timeout_secs'][0]
    return result

  def ng_builders(self):
    result = []
    try_bucket = self.get_bucket_by_suffix('try')
    for builder in self.builders(try_bucket):
      builder_name = self.builder_name(builder)
      if builder_name.endswith('_ng') and builder_name[:-3] not in UNRULY_BUILDERS:
        result.append(builder)
    return result

  def try_builders(self):
    result = []
    try_bucket = self.get_bucket_by_suffix('try')
    for builder in self.builders(try_bucket):
      builder_name = self.builder_name(builder)
      if not builder_name.endswith('_ng') and builder_name[:-3] not in UNRULY_BUILDERS:
        result.append(builder)
    return result

  def consolidate_builder(self, builder):
    builder_props = self.consolidate_mixins(builder) + builder.items()
    consolidated = self.duplicate_key_dict_builder(builder_props)
    return consolidated

  def consolidate_mixins(self, referer):
    mixins = self.mixins()
    consolidated_list = []
    for ref in referer.pop('mixins', []):
      mixin_copy = mixins[ref].copy()
      inner_list = self.consolidate_mixins(mixin_copy)
      del mixin_copy['name']
      consolidated_list = consolidated_list + inner_list + mixin_copy.items()
    return consolidated_list

  def duplicate_key_dict_builder(self, lst):
    res = dict()
    for k,v in lst:
      if k in res:
        res[k] = res[k] + v
      else:
        res[k] = v
    return res

  def consolidate_recipe(self, recipe):
    as_list = []
    for r in recipe:
      as_list.extend(r.items())
    return self.duplicate_key_dict_builder(as_list)

  def add_props(self, p_dict, p_list):
    for item in p_list:
      if type(item) is str:
        splited = item.split(":", 1)
        p_dict[splited[0]] = self.flatten_value(splited[1])
      elif type(item) is dict:
        for k,v in item.items():
          p_dict[k] = self.flatten_value(v)
      else:
        print("UNTREATED PROPERTY TYPE")

  def flatten_value(self, value):
    if type(value) is dict:
      res = dict()
      for k, v in value.items():
        res[k] = self.flatten_value(v)
      return res
    elif type(value) is list and len(value) == 1:
      return self.flatten_value(value[0])
    elif value == "true":
      return True
    elif value == "false":
      return False
    elif type(value) is str and value.isdigit():
      return int(value)
    else:
      return value

class SchedulerCfg:
  def __init__(self):
    self.cfg = prototext.prototext2dict('luci-scheduler.cfg')
    self.jobs = self.jobs_dict()
    self.builder2job = self.builder2job_dict()
    self.builder2trigger = self.builder2trigger_dict()
  
  def jobs_dict(self):
    result = dict()
    for job in self.cfg['job']:
      name = job['id'][0]
      result[name] = job
    return result

  def builder2job_dict(self):
    result = dict()
    for job in self.cfg['job']:
      bb = job['buildbucket'][0]
      key = (bb['bucket'][0][8:],  bb['builder'][0])
      result[key] = job
    return result

  def builder2trigger_dict(self):
    result = dict()
    for trigger in self.cfg['trigger']:
      for job_name in trigger['triggers']:
        job = self.jobs[job_name]
        bb = job['buildbucket'][0]
        key = (bb['bucket'][0][8:],  bb['builder'][0])
        result[key] = trigger
    return result

  def triggerd_by(self, bucket_name, builder_name):
    trigger = self.builder2trigger.get((bucket_name, builder_name), None)
    if trigger:
      return "['%s']" % trigger['id'][0]
    return None

  def job(self, bucket_name, builder_name):
    return self.builder2job.get((bucket_name, builder_name), None)


class CommitQueueCfg:
  def __init__(self):
    self.cfg = prototext.prototext2dict('commit-queue.cfg')
    self.map_builders()

  def map_builders(self):
    self.builders_dict = dict()
    for cg in self.cfg['config_groups']:
      if cg['name'][0]== 'v8-cq':
        for tj in cg['verifiers'][0]['tryjob'][0]['builders']:
          [project, bucket, name] = tj['name'][0].split('/')
          self.builders_dict[(bucket, name)] = self.properties(tj)

  def properties(self, try_job):
    result = dict()
    try_job.pop('name')
    cancel_stale = try_job.pop('cancel_stale', None)
    if cancel_stale:
      result['cancel_stale'] = cancel_stale[0] == "YES"
    experiment_percentage = try_job.pop('experiment_percentage', None)
    if experiment_percentage:
      result['experiment_percentage'] = int(experiment_percentage[0])
    includable_only = try_job.pop('includable_only', None)
    if includable_only:
      result['includable_only'] = includable_only[0]
    disable_reuse = try_job.pop('disable_reuse', None)
    if disable_reuse:
      result['disable_reuse'] = disable_reuse[0]
    location_regexp = try_job.pop('location_regexp', None)
    if location_regexp:
      result['location_regexp'] = location_regexp
    triggered_by = try_job.pop('triggered_by', None)
    if triggered_by:
      pass#result['triggered-by'] = triggered_by
    return result


class MiloCfg:
  def __init__(self):
    self.cfg = prototext.prototext2dict('luci-milo.cfg')
